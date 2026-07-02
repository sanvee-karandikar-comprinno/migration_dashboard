"""
core/cdc/postgresql_cdc.py
==========================
PostgreSQL CDC implementation using timestamp-based change detection.

Strategy:
  Polls tables that have a 'modified_date', 'updated_at', or similar timestamp column.
  Detects rows modified after the last checkpoint and emits INSERT events.

  This is a polling-based approach (not true log-based CDC) that works on any
  PostgreSQL installation without requiring logical replication setup.

  For true real-time CDC, PostgreSQL logical decoding (wal2json) would be needed,
  but that requires server-side configuration which we cannot assume.
"""

from datetime import datetime
from sqlalchemy import text
from sqlalchemy.engine import Engine

from core.cdc.base_cdc import BaseCDC, CDCEvent


# Common column names that indicate a modification timestamp
TIMESTAMP_COLUMNS = [
    "modifieddate", "modified_date", "updated_at", "updatedat",
    "last_modified", "lastmodified", "modified", "updated",
    "timestamp", "change_date", "changedate",
]


class PostgreSQLCdc(BaseCDC):

    def __init__(self, engine: Engine, database_name: str):
        super().__init__(engine, database_name)
        self.engine = engine
        self._tables: list[str] = []
        self._checkpoint: str = ""

    def start(self, tables: list[str] | None = None) -> None:
        """Initialize CDC — store table list for polling."""
        self._tables = tables or []

    def capture(self, from_checkpoint: str = ""):
        """
        Polls tables for changes since the checkpoint timestamp.
        Yields CDCEvent for each changed row detected.
        """
        # Parse checkpoint as a datetime, or use epoch if none
        if from_checkpoint:
            try:
                last_sync = datetime.fromisoformat(from_checkpoint)
            except ValueError:
                last_sync = datetime(2000, 1, 1)
        else:
            last_sync = datetime(2000, 1, 1)

        for table_ref in self._tables:
            parts = table_ref.split(".")
            if len(parts) == 2:
                schema, table = parts[0].lower(), parts[1].lower()
            else:
                schema, table = "public", parts[0].lower()

            # Find a timestamp column in this table
            ts_col = self._find_timestamp_column(schema, table)
            if not ts_col:
                continue  # No timestamp column — cannot detect changes

            # Query rows modified after last checkpoint
            try:
                query = text(f'''
                    SELECT * FROM "{schema}"."{table}"
                    WHERE "{ts_col}" > :last_sync
                    ORDER BY "{ts_col}" ASC
                    LIMIT 1000
                ''')

                with self.engine.connect() as conn:
                    result = conn.execute(query, {"last_sync": last_sync})
                    columns = list(result.keys())

                    for row in result:
                        row_dict = dict(zip(columns, row))
                        event = CDCEvent(
                            operation="INSERT",
                            schema_name=schema,
                            table_name=table,
                            data=row_dict,
                            old_data=None,
                            checkpoint=datetime.utcnow().isoformat(),
                            event_time=datetime.utcnow(),
                        )
                        self._checkpoint = event.checkpoint
                        yield event

            except Exception:
                # Table might not exist or have permission issues — skip
                continue

    def stop(self) -> None:
        """Nothing to clean up for polling-based CDC."""
        pass

    def get_checkpoint(self) -> str:
        return self._checkpoint

    def _find_timestamp_column(self, schema: str, table: str) -> str | None:
        """Checks if the table has a recognizable timestamp column for change detection."""
        try:
            query = text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :table
                AND data_type IN ('timestamp without time zone', 'timestamp with time zone', 'date')
                ORDER BY ordinal_position
            """)

            with self.engine.connect() as conn:
                result = conn.execute(query, {"schema": schema, "table": table})
                available_cols = [row[0].lower() for row in result]

            # Match against known timestamp column names
            for candidate in TIMESTAMP_COLUMNS:
                if candidate in available_cols:
                    return candidate

            # If no known name matched, use the first timestamp column found
            if available_cols:
                return available_cols[0]

            return None

        except Exception:
            return None
