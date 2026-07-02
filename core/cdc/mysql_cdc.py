"""
core/cdc/mysql_cdc.py
=====================
MySQL CDC implementation using timestamp-based change detection.

Strategy:
  Same as PostgreSQL CDC — polls tables with timestamp columns
  (modified_date, updated_at, etc.) for rows changed since last checkpoint.

  For true binlog-based CDC, mysql-replication library would be needed,
  but that requires REPLICATION SLAVE privilege which we cannot assume.
"""

from datetime import datetime
from sqlalchemy import text
from sqlalchemy.engine import Engine

from core.cdc.base_cdc import BaseCDC, CDCEvent


TIMESTAMP_COLUMNS = [
    "modifieddate", "modified_date", "updated_at", "updatedat",
    "last_modified", "lastmodified", "modified", "updated",
    "timestamp", "change_date", "changedate",
]


class MySQLCdc(BaseCDC):

    def __init__(self, engine: Engine, database_name: str):
        super().__init__(engine, database_name)
        self.engine = engine
        self._tables: list[str] = []
        self._checkpoint: str = ""

    def start(self, tables: list[str] | None = None) -> None:
        self._tables = tables or []

    def capture(self, from_checkpoint: str = ""):
        """Polls tables for changes since the checkpoint timestamp."""
        if from_checkpoint:
            try:
                last_sync = datetime.fromisoformat(from_checkpoint)
            except ValueError:
                last_sync = datetime(2000, 1, 1)
        else:
            last_sync = datetime(2000, 1, 1)

        for table_ref in self._tables:
            parts = table_ref.split(".")
            table = parts[-1].lower()

            ts_col = self._find_timestamp_column(table)
            if not ts_col:
                continue

            try:
                query = text(f"SELECT * FROM `{table}` WHERE `{ts_col}` > :last_sync ORDER BY `{ts_col}` ASC LIMIT 1000")

                with self.engine.connect() as conn:
                    result = conn.execute(query, {"last_sync": last_sync})
                    columns = list(result.keys())

                    for row in result:
                        row_dict = dict(zip(columns, row))
                        event = CDCEvent(
                            operation="INSERT",
                            schema_name="",
                            table_name=table,
                            data=row_dict,
                            old_data=None,
                            checkpoint=datetime.utcnow().isoformat(),
                            event_time=datetime.utcnow(),
                        )
                        self._checkpoint = event.checkpoint
                        yield event

            except Exception:
                continue

    def stop(self) -> None:
        pass

    def get_checkpoint(self) -> str:
        return self._checkpoint

    def _find_timestamp_column(self, table: str) -> str | None:
        """Finds a timestamp column in the table."""
        try:
            query = text("""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :db_name AND TABLE_NAME = :table
                AND DATA_TYPE IN ('datetime', 'timestamp', 'date')
                ORDER BY ORDINAL_POSITION
            """)

            with self.engine.connect() as conn:
                result = conn.execute(query, {"db_name": self.database_name, "table": table})
                available_cols = [row[0].lower() for row in result]

            for candidate in TIMESTAMP_COLUMNS:
                if candidate in available_cols:
                    return candidate

            if available_cols:
                return available_cols[0]

            return None

        except Exception:
            return None
