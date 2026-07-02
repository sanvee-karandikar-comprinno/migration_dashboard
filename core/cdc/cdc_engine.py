"""
Generic CDC Engine.

Architecture:
    Source Database
        ↓
    CDC Adapter (MSSQL | MongoDB)
        ↓
    Event Queue (in-memory deque)
        ↓
    Target Applier
        ↓
    Target Database

Supports:
  - Full initial load + incremental CDC
  - Restartability via checkpoint file
  - Failure recovery (skip bad events, continue)
  - Event stats
"""
import json
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable

from core.cdc.base_cdc import BaseCDC, CDCEvent


class CDCEngine:

    def __init__(
        self,
        source_cdc: BaseCDC,
        apply_event: Callable[[CDCEvent], None],
        checkpoint_file: str = "reports/cdc_checkpoint.json",
        queue_maxsize: int = 10_000,
    ):
        self.source_cdc = source_cdc
        self.apply_event = apply_event
        self.checkpoint_file = Path(checkpoint_file)
        self._queue: deque[CDCEvent] = deque(maxlen=queue_maxsize)
        self._running = False
        self._stats = {
            "events_captured": 0,
            "events_applied": 0,
            "events_failed": 0,
            "last_event_time": None,
            "last_checkpoint": "",
            "started_at": None,
        }
        self._lock = threading.Lock()

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def start(self, tables: list[str] | None = None) -> None:
        self._stats["started_at"] = datetime.utcnow().isoformat()
        self.source_cdc.start(tables)

    def stop(self) -> None:
        self._running = False
        self.source_cdc.stop()

    # ─────────────────────────────────────────────────────────────────────────
    # Main run loop (blocking)
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, tables: list[str] | None = None) -> dict:
        """
        Blocking run: starts CDC, captures events, applies them.
        Returns stats on completion.
        """
        checkpoint = self._load_checkpoint()
        self._running = True

        try:
            self.start(tables)

            for event in self.source_cdc.capture(from_checkpoint=checkpoint):
                if not self._running:
                    break

                with self._lock:
                    self._queue.append(event)
                    self._stats["events_captured"] += 1
                    self._stats["last_event_time"] = event.event_time.isoformat()

                self._apply_event_safe(event)
                self._save_checkpoint(event.checkpoint)

        finally:
            self.stop()

        return self.get_stats()

    def run_in_background(self, tables: list[str] | None = None) -> threading.Thread:
        """Start CDC in a background thread. Returns the thread."""
        thread = threading.Thread(target=self.run, args=(tables,), daemon=True)
        thread.start()
        return thread

    # ─────────────────────────────────────────────────────────────────────────
    # Event application
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_event_safe(self, event: CDCEvent) -> None:
        try:
            self.apply_event(event)
            with self._lock:
                self._stats["events_applied"] += 1
                self._stats["last_checkpoint"] = event.checkpoint
        except Exception as error:
            with self._lock:
                self._stats["events_failed"] += 1
            print(f"CDC apply error [{event.operation}] {event.schema_name}.{event.table_name}: {error}")

    # ─────────────────────────────────────────────────────────────────────────
    # Checkpoint persistence
    # ─────────────────────────────────────────────────────────────────────────

    def _load_checkpoint(self) -> str:
        if self.checkpoint_file.exists():
            try:
                data = json.loads(self.checkpoint_file.read_text())
                return data.get("checkpoint", "")
            except Exception:
                pass
        return ""

    def _save_checkpoint(self, checkpoint: str) -> None:
        if not checkpoint:
            return
        try:
            self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            self.checkpoint_file.write_text(json.dumps({
                "checkpoint": checkpoint,
                "saved_at": datetime.utcnow().isoformat(),
            }))
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def get_queue_size(self) -> int:
        return len(self._queue)


# ─────────────────────────────────────────────────────────────────────────────
# Factory helper
# ─────────────────────────────────────────────────────────────────────────────

def create_cdc_engine(
    source_type: str,
    source_connection,
    database_name: str,
    apply_event: Callable[[CDCEvent], None],
    checkpoint_file: str = "reports/cdc_checkpoint.json",
) -> CDCEngine:
    """
    Factory that returns a CDCEngine wired to the appropriate adapter.
    Supports: mssql, mysql, postgresql, mongodb
    """
    source_type = source_type.lower()

    if source_type == "mssql":
        from core.cdc.mssql_cdc import MSSQLCdc
        adapter = MSSQLCdc(engine=source_connection, database_name=database_name)

    elif source_type == "postgresql":
        from core.cdc.postgresql_cdc import PostgreSQLCdc
        adapter = PostgreSQLCdc(engine=source_connection, database_name=database_name)

    elif source_type == "mysql":
        from core.cdc.mysql_cdc import MySQLCdc
        adapter = MySQLCdc(engine=source_connection, database_name=database_name)

    elif source_type == "mongodb":
        from core.cdc.mongodb_cdc import MongoDBCdc
        adapter = MongoDBCdc(client=source_connection, database_name=database_name)

    else:
        raise ValueError(
            f"CDC not implemented for source type '{source_type}'. "
            "Supported: mssql, mysql, postgresql, mongodb."
        )

    return CDCEngine(
        source_cdc=adapter,
        apply_event=apply_event,
        checkpoint_file=checkpoint_file,
    )
