"""
core/cdc/mongo_applier.py
=========================
Applies CDC events to MongoDB collections.

This module connects the CDC engine to a MongoDB target:
- INSERT events → collection.insert_one()
- UPDATE events → collection.update_one()
- DELETE events → collection.delete_one()

Used for real-time/incremental sync from SQL databases to MongoDB.

Architecture:
    SQL Source (MSSQL/MySQL/PostgreSQL)
        ↓ CDC Engine captures changes
    CDCEvent (INSERT/UPDATE/DELETE)
        ↓ MongoApplier processes event
    MongoDB Target (insert/update/delete documents)

Usage:
    from core.cdc.mongo_applier import MongoApplier
    from core.cdc.cdc_engine import create_cdc_engine

    applier = MongoApplier(mongo_client, "target_db_name")
    engine = create_cdc_engine("mssql", src_engine, "source_db", applier.apply_event)
    stats = engine.run(tables=["HumanResources.Employee"])
"""

import logging
from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID
from typing import Any

from pymongo import MongoClient
from core.cdc.base_cdc import CDCEvent

logger = logging.getLogger(__name__)


class MongoApplier:
    """
    Applies CDC events from a SQL source to MongoDB collections.
    
    Naming convention for collections: schema_tablename (lowercase, flat)
    Example: HumanResources.Employee → humanresources_employee
    
    Uses _cdc_id field to track the primary key for updates/deletes.
    If no primary key is available, uses the full document for matching.
    """

    def __init__(self, mongo_client: MongoClient, target_database: str, log_callback=None):
        """
        Args:
            mongo_client: Connected PyMongo client
            target_database: Name of the MongoDB database to write to
            log_callback: Optional function for progress messages
        """
        self.client = mongo_client
        self.db = mongo_client[target_database]
        self.log_callback = log_callback
        self._stats = {
            "inserts": 0,
            "updates": 0,
            "deletes": 0,
            "errors": 0,
        }

    def apply_event(self, event: CDCEvent) -> None:
        """
        Applies a single CDC event to the target MongoDB collection.
        This is the callback function passed to CDCEngine.
        
        Args:
            event: CDCEvent with operation, schema, table, and data
        """
        collection_name = self._get_collection_name(event.schema_name, event.table_name)
        collection = self.db[collection_name]

        try:
            if event.operation == "INSERT":
                self._apply_insert(collection, event)
            elif event.operation == "UPDATE":
                self._apply_update(collection, event)
            elif event.operation == "DELETE":
                self._apply_delete(collection, event)
            else:
                # DDL events (CREATE_TABLE, DROP_TABLE) — log but skip
                logger.debug(f"CDC DDL event skipped: {event.operation} on {collection_name}")
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"CDC apply error on {collection_name}: {e}")

    def _apply_insert(self, collection, event: CDCEvent):
        """Inserts a new document into the collection."""
        doc = self._convert_to_document(event.data)
        # Add metadata for tracking
        doc["_cdc_timestamp"] = event.event_time
        doc["_cdc_operation"] = "INSERT"
        collection.insert_one(doc)
        self._stats["inserts"] += 1

    def _apply_update(self, collection, event: CDCEvent):
        """Updates an existing document. Uses old_data to find the document."""
        new_doc = self._convert_to_document(event.data)
        new_doc["_cdc_timestamp"] = event.event_time
        new_doc["_cdc_operation"] = "UPDATE"

        # Build filter to find the document to update
        filter_doc = self._build_filter(event)

        if filter_doc:
            result = collection.replace_one(filter_doc, new_doc, upsert=True)
            if result.modified_count > 0 or result.upserted_id:
                self._stats["updates"] += 1
        else:
            # Cannot determine which doc to update — insert as new
            collection.insert_one(new_doc)
            self._stats["inserts"] += 1

    def _apply_delete(self, collection, event: CDCEvent):
        """Deletes a document from the collection."""
        filter_doc = self._build_filter(event)

        if filter_doc:
            result = collection.delete_one(filter_doc)
            if result.deleted_count > 0:
                self._stats["deletes"] += 1
        else:
            logger.warning(f"CDC DELETE: No filter could be built for {event.table_name}")

    def _build_filter(self, event: CDCEvent) -> dict:
        """
        Builds a MongoDB filter to find the target document.
        Uses old_data (pre-change values) if available, otherwise uses
        primary key fields from the new data.
        """
        # If old_data is available, use it to match
        source_data = event.old_data if event.old_data else event.data
        if not source_data:
            return {}

        # Try to use common PK field names as filter
        pk_candidates = ["id", "Id", "ID", "BusinessEntityID", "ProductID",
                         "SalesOrderID", "CustomerID"]

        filter_doc = {}
        for pk in pk_candidates:
            if pk in source_data and source_data[pk] is not None:
                filter_doc[pk.lower()] = self._convert_value(source_data[pk])
                return filter_doc

        # Fallback: use first non-null field from old data
        for key, val in source_data.items():
            if val is not None:
                filter_doc[key.lower()] = self._convert_value(val)
                if len(filter_doc) >= 2:
                    break

        return filter_doc

    def _convert_to_document(self, data: dict) -> dict:
        """Converts a row dict to a MongoDB-compatible document."""
        doc = {}
        for key, value in data.items():
            doc[key.lower()] = self._convert_value(value)
        return doc

    def _convert_value(self, value: Any) -> Any:
        """Converts Python/SQL values to MongoDB-compatible types."""
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, time):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, bytes):
            return value.hex()
        return value

    def _get_collection_name(self, schema_name: str, table_name: str) -> str:
        """Returns the MongoDB collection name from schema + table."""
        schema = schema_name.lower() if schema_name else ""
        tbl = table_name.lower()
        if schema and schema not in ("dbo", "public"):
            return f"{schema}_{tbl}"
        return tbl

    def get_stats(self) -> dict:
        """Returns CDC application statistics."""
        return dict(self._stats)

    def reset_stats(self):
        """Resets the stats counters."""
        self._stats = {"inserts": 0, "updates": 0, "deletes": 0, "errors": 0}
