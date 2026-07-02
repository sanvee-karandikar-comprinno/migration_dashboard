"""
Base CDC interface. All CDC implementations must extend this class.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CDCEvent:
    operation: str          # INSERT | UPDATE | DELETE | CREATE_TABLE | DROP_TABLE
    schema_name: str
    table_name: str
    data: dict[str, Any]
    old_data: dict[str, Any] | None = None
    checkpoint: str = ""
    event_time: datetime = field(default_factory=datetime.utcnow)


class BaseCDC(ABC):
    """
    Abstract base for CDC sources.
    Subclasses implement capture() which yields CDCEvent instances.
    """

    def __init__(self, connection, database_name: str):
        self.connection = connection
        self.database_name = database_name

    @abstractmethod
    def start(self, tables: list[str] | None = None) -> None:
        """Initialise the CDC session (enable CDC, open streams, etc.)."""

    @abstractmethod
    def capture(self, from_checkpoint: str = ""):
        """Yield CDCEvent instances from the current position."""

    @abstractmethod
    def stop(self) -> None:
        """Clean up resources."""

    @abstractmethod
    def get_checkpoint(self) -> str:
        """Return the current checkpoint / LSN / resume token."""
