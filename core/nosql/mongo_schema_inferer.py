"""
core/nosql/mongo_schema_inferer.py
==================================
Infers a SQL-compatible schema from MongoDB collection documents.

MongoDB is schemaless — documents in the same collection can have different fields.
This module samples documents and builds a "best guess" schema suitable for SQL.

Approach:
- Samples up to 100 documents from the collection
- Collects all unique field names
- Maps Python/BSON types to SQL types for the target database
- Flattens nested objects into parent_child naming
"""

import logging
from datetime import datetime
from bson import ObjectId, Decimal128

logger = logging.getLogger(__name__)

# Maps Python types (from MongoDB documents) to SQL types
PYTHON_TO_SQL = {
    "mysql": {
        "str": "LONGTEXT",
        "int": "BIGINT",
        "float": "DOUBLE",
        "bool": "TINYINT(1)",
        "datetime": "DATETIME(6)",
        "ObjectId": "VARCHAR(24)",
        "Decimal128": "DECIMAL(38,10)",
        "bytes": "LONGBLOB",
        "list": "JSON",
        "dict": "JSON",
        "NoneType": "LONGTEXT",
    },
    "postgresql": {
        "str": "TEXT",
        "int": "BIGINT",
        "float": "DOUBLE PRECISION",
        "bool": "BOOLEAN",
        "datetime": "TIMESTAMP",
        "ObjectId": "VARCHAR(24)",
        "Decimal128": "NUMERIC(38,10)",
        "bytes": "BYTEA",
        "list": "JSONB",
        "dict": "JSONB",
        "NoneType": "TEXT",
    },
    "mssql": {
        "str": "NVARCHAR(MAX)",
        "int": "BIGINT",
        "float": "FLOAT",
        "bool": "BIT",
        "datetime": "DATETIME2",
        "ObjectId": "NVARCHAR(24)",
        "Decimal128": "DECIMAL(38,10)",
        "bytes": "VARBINARY(MAX)",
        "list": "NVARCHAR(MAX)",
        "dict": "NVARCHAR(MAX)",
        "NoneType": "NVARCHAR(MAX)",
    },
}


def infer_collection_schema(collection, target_type: str, sample_size: int = 100) -> dict:
    """
    Infers a SQL column schema from MongoDB documents.
    
    Args:
        collection: PyMongo collection object
        target_type: Target SQL type ('mysql', 'postgresql', 'mssql')
        sample_size: Number of documents to sample (default 100)
        
    Returns:
        Dictionary of {column_name: sql_type} or empty dict if collection is empty
    """
    target = target_type.lower()
    type_map = PYTHON_TO_SQL.get(target, PYTHON_TO_SQL["postgresql"])
    
    # Sample documents
    samples = list(collection.find().limit(sample_size))
    if not samples:
        return {}
    
    # Collect all fields and their types
    field_types = {}
    
    for doc in samples:
        flat = _flatten_for_schema(doc)
        for field_name, value in flat.items():
            python_type = _get_type_name(value)
            
            if field_name not in field_types:
                field_types[field_name] = set()
            field_types[field_name].add(python_type)
    
    # Build schema: choose the most appropriate SQL type for each field
    schema = {}
    for field_name, types in field_types.items():
        # Sanitize field name for SQL
        safe_name = _sanitize_column_name(field_name)
        
        # If multiple types detected, use the most general one (TEXT/NVARCHAR)
        if len(types) > 2 or "NoneType" in types and len(types) > 2:
            schema[safe_name] = type_map.get("str", "TEXT")
        else:
            # Use the first non-None type
            chosen_type = "str"
            for t in types:
                if t != "NoneType":
                    chosen_type = t
                    break
            schema[safe_name] = type_map.get(chosen_type, type_map["str"])
    
    return schema


def _flatten_for_schema(doc: dict, prefix: str = "") -> dict:
    """Flattens document for schema inference (same as data migration)."""
    flat = {}
    for key, value in doc.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}_{key}"
        
        if key == "_id":
            flat["_id"] = value
        elif isinstance(value, dict):
            flat.update(_flatten_for_schema(value, full_key))
        elif isinstance(value, list):
            flat[full_key] = value
        else:
            flat[full_key] = value
    
    return flat


def _get_type_name(value) -> str:
    """Gets a simplified type name for schema inference."""
    if value is None:
        return "NoneType"
    if isinstance(value, ObjectId):
        return "ObjectId"
    if isinstance(value, Decimal128):
        return "Decimal128"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, bytes):
        return "bytes"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "str"


def _sanitize_column_name(name: str) -> str:
    """Makes a field name safe for SQL column naming."""
    # Replace dots, spaces, special chars with underscores
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    # Ensure it doesn't start with a number
    if safe and safe[0].isdigit():
        safe = f"f_{safe}"
    return safe.lower()
