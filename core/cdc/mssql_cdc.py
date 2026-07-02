"""
SQL Server CDC implementation.

Strategy:
  1. Check if the database has native CDC enabled (sys.databases.is_cdc_enabled).
  2. If yes  → use transaction log CDC (sys.fn_cdc_get_all_changes_*), LSN tracking.
  3. If no   → fall back to trigger-based CDC using a _cdc_changes shadow table.

Trigger fallback works on SQL Server Express / editions where CDC is not licensed.
"""
import json
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.engine import Engine

from core.cdc.base_cdc import BaseCDC, CDCEvent


class MSSQLCdc(BaseCDC):

    def __init__(self, engine: Engine, database_name: str):
        super().__init__(engine, database_name)
        self.engine = engine
        self._lsn: str = ""
        self._use_native_cdc: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def start(self, tables: list[str] | None = None) -> None:
        if self._is_native_cdc_enabled():
            self._use_native_cdc = True
            if tables:
                for table in tables:
                    self._enable_native_cdc_for_table(table)
        else:
            self._use_native_cdc = False
            self._create_cdc_shadow_table()
            if tables:
                for table in tables:
                    self._install_trigger(table)

    def capture(self, from_checkpoint: str = ""):
        if self._use_native_cdc:
            yield from self._capture_native(from_checkpoint)
        else:
            yield from self._capture_triggers(from_checkpoint)

    def stop(self) -> None:
        pass  # Connections managed externally

    def get_checkpoint(self) -> str:
        return self._lsn

    # ─────────────────────────────────────────────────────────────────────────
    # Native CDC
    # ─────────────────────────────────────────────────────────────────────────

    def _is_native_cdc_enabled(self) -> bool:
        query = "SELECT is_cdc_enabled FROM sys.databases WHERE name = DB_NAME();"
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query)).fetchone()
                return bool(result[0]) if result else False
        except Exception:
            return False

    def _enable_native_cdc_for_table(self, table: str) -> None:
        schema, tbl = self._split_table(table)
        try:
            with self.engine.connect() as conn:
                conn.execute(text(f"""
                    EXEC sys.sp_cdc_enable_table
                        @source_schema = '{schema}',
                        @source_name   = '{tbl}',
                        @role_name     = NULL;
                """))
                conn.commit()
        except Exception:
            pass  # Already enabled or insufficient permissions

    def _capture_native(self, from_checkpoint: str = ""):
        """
        Read changes from cdc.* tables using sys.fn_cdc_get_all_changes_*.
        Yields CDCEvent for each changed row.
        """
        with self.engine.connect() as conn:
            # Get current max LSN
            max_lsn_row = conn.execute(
                text("SELECT sys.fn_cdc_get_max_lsn()")
            ).fetchone()
            if not max_lsn_row:
                return

            max_lsn = max_lsn_row[0]

            # Determine start LSN
            if from_checkpoint:
                start_lsn = bytes.fromhex(from_checkpoint)
            else:
                start_lsn_row = conn.execute(
                    text("SELECT sys.fn_cdc_get_min_lsn('dbo_SalesOrderHeader')")
                ).fetchone()
                start_lsn = start_lsn_row[0] if start_lsn_row else max_lsn

            # Iterate all CDC capture instances
            instances = conn.execute(
                text("SELECT capture_instance FROM cdc.change_tables;")
            ).fetchall()

            for (instance,) in instances:
                schema_part, table_part = (instance.split("_", 1) + [""])[:2]
                try:
                    rows = conn.execute(text(f"""
                        SELECT *
                        FROM cdc.fn_cdc_get_all_changes_{instance}(
                            :start_lsn, :max_lsn, N'all'
                        )
                    """), {"start_lsn": start_lsn, "max_lsn": max_lsn}).fetchall()

                    for row in rows:
                        row_dict = dict(row._mapping)
                        op_code = row_dict.pop("__$operation", 2)
                        row_dict.pop("__$start_lsn", None)
                        row_dict.pop("__$seqval", None)
                        row_dict.pop("__$update_mask", None)

                        op = {1: "DELETE", 2: "INSERT", 3: "UPDATE", 4: "UPDATE"}.get(op_code, "INSERT")
                        lsn_bytes = max_lsn
                        self._lsn = lsn_bytes.hex() if isinstance(lsn_bytes, bytes) else str(lsn_bytes)

                        yield CDCEvent(
                            operation=op,
                            schema_name=schema_part,
                            table_name=table_part,
                            data=row_dict,
                            checkpoint=self._lsn,
                        )
                except Exception:
                    continue

    # ─────────────────────────────────────────────────────────────────────────
    # Trigger-based fallback
    # ─────────────────────────────────────────────────────────────────────────

    def _create_cdc_shadow_table(self) -> None:
        sql = """
        IF OBJECT_ID('dbo._cdc_changes', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo._cdc_changes (
                id            BIGINT IDENTITY(1,1) PRIMARY KEY,
                schema_name   NVARCHAR(128),
                table_name    NVARCHAR(128),
                operation     NVARCHAR(10),
                row_data      NVARCHAR(MAX),
                changed_at    DATETIME2 DEFAULT GETDATE()
            );
        END
        """
        with self.engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()

    def _install_trigger(self, table: str) -> None:
        schema, tbl = self._split_table(table)
        trigger_name = f"_cdc_trg_{schema}_{tbl}"

        sql = f"""
        IF OBJECT_ID('{schema}.{trigger_name}', 'TR') IS NULL
        BEGIN
            EXEC('
                CREATE TRIGGER [{schema}].[{trigger_name}]
                ON [{schema}].[{tbl}]
                AFTER INSERT, UPDATE, DELETE
                AS
                BEGIN
                    SET NOCOUNT ON;
                    IF EXISTS (SELECT 1 FROM inserted) AND EXISTS (SELECT 1 FROM deleted)
                        INSERT INTO dbo._cdc_changes (schema_name, table_name, operation, row_data)
                        SELECT ''{schema}'', ''{tbl}'', ''UPDATE'',
                               (SELECT * FROM inserted FOR JSON AUTO)
                    ELSE IF EXISTS (SELECT 1 FROM inserted)
                        INSERT INTO dbo._cdc_changes (schema_name, table_name, operation, row_data)
                        SELECT ''{schema}'', ''{tbl}'', ''INSERT'',
                               (SELECT * FROM inserted FOR JSON AUTO)
                    ELSE
                        INSERT INTO dbo._cdc_changes (schema_name, table_name, operation, row_data)
                        SELECT ''{schema}'', ''{tbl}'', ''DELETE'',
                               (SELECT * FROM deleted FOR JSON AUTO)
                END
            ')
        END
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception:
            pass

    def _capture_triggers(self, from_checkpoint: str = ""):
        last_id = int(from_checkpoint) if from_checkpoint else 0

        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, schema_name, table_name, operation, row_data, changed_at
                FROM dbo._cdc_changes
                WHERE id > :last_id
                ORDER BY id
            """), {"last_id": last_id}).fetchall()

            for row in rows:
                self._lsn = str(row[0])
                try:
                    data = json.loads(row[3]) if row[3] else {}
                    if isinstance(data, list) and data:
                        data = data[0]
                except Exception:
                    data = {}

                yield CDCEvent(
                    operation=row[2],
                    schema_name=row[1],
                    table_name=row[2],
                    data=data,
                    checkpoint=self._lsn,
                    event_time=row[4] if isinstance(row[4], datetime) else datetime.utcnow(),
                )

    @staticmethod
    def _split_table(table: str) -> tuple[str, str]:
        parts = table.replace("[", "").replace("]", "").split(".")
        if len(parts) == 2:
            return parts[0], parts[1]
        return "dbo", parts[0]
