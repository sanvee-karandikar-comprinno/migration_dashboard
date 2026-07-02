"""
core/nosql/mongo_to_sql_migrator.py
===================================
Migrates data from MongoDB collections into SQL tables.

Steps:
1. Infer schema from MongoDB documents (sampling)
2. Create SQL tables based on inferred schema
3. Flatten nested documents and insert data in batches

LIMITATIONS:
- Deeply nested objects are flattened (parent_child naming)
- Arrays are stored as JSON strings
- MongoDB's flexible schema means some documents may have different fields
"""

import logging
import json
from datetime import datetime
from bson import ObjectId

from sqlalchemy import text
from sqlalchemy.engine import Engine
from pymongo import MongoClient

from core.nosql.mongo_schema_inferer import infer_collection_schema

logger = logging.getLogger(__name__)


def migrate_mongodb_to_sql(
    mongo_client: MongoClient,
    target_engine: Engine,
    source_database: str,
    target_database: str,
    target_type: str,
    batch_size: int = 1000,
    log_callback=None,
) -> dict:
    """
    Migrates all MongoDB collections to SQL tables.
    
    Args:
        mongo_client: Connected MongoClient
        target_engine: SQLAlchemy engine for target SQL database
        source_database: MongoDB database name
        target_database: Target SQL database name
        target_type: Target DB type ('mssql', 'mysql', 'postgresql')
        batch_size: Rows per batch insert
        log_callback: Optional progress callback
        
    Returns:
        Migration result dictionary
    """
    db = mongo_client[source_database]
    collections = db.list_collection_names()
    
    result = {
        "status": "completed",
        "collections_migrated": 0,
        "collections_failed": 0,
        "total_rows": 0,
        "table_results": [],
    }
    
    for coll_name in sorted(collections):
        msg = f"Migrating collection: {coll_name}"
        logger.info(msg)
        if log_callback:
            log_callback(msg)
        
        try:
            collection = db[coll_name]
            
            # Step 1: Infer schema from documents
            schema = infer_collection_schema(collection, target_type)
            if not schema:
                result["table_results"].append({
                    "collection_name": coll_name,
                    "status": "skipped",
                    "rows": 0,
                    "error": "Empty collection",
                })
                continue
            
            # Step 2: Create SQL table
            table_name = _sanitize_table_name(coll_name, target_type)
            create_sql = _build_create_table(table_name, schema, target_type)
            
            with target_engine.connect() as conn:
                # Drop if exists for clean migration
                drop_sql = _build_drop_table(table_name, target_type)
                try:
                    conn.execute(text(drop_sql))
                    conn.commit()
                except Exception:
                    pass
                
                conn.execute(text(create_sql))
                conn.commit()
            
            # Step 3: Insert data in batches
            rows_inserted = 0
            col_names = list(schema.keys())
            
            batch = []
            for doc in collection.find():
                flat_doc = _flatten_document(doc)
                row = {col: flat_doc.get(col) for col in col_names}
                batch.append(row)
                
                if len(batch) >= batch_size:
                    _insert_batch(target_engine, table_name, col_names, batch, target_type)
                    rows_inserted += len(batch)
                    batch = []
            
            if batch:
                _insert_batch(target_engine, table_name, col_names, batch, target_type)
                rows_inserted += len(batch)
            
            result["collections_migrated"] += 1
            result["total_rows"] += rows_inserted
            result["table_results"].append({
                "collection_name": coll_name,
                "table_name": table_name,
                "status": "success",
                "rows": rows_inserted,
                "error": None,
            })
            
        except Exception as e:
            result["collections_failed"] += 1
            result["table_results"].append({
                "collection_name": coll_name,
                "status": "failed",
                "rows": 0,
                "error": str(e),
            })
            logger.error(f"Failed: {coll_name}: {e}")
    
    if result["collections_failed"] > 0:
        result["status"] = "completed_with_errors"
    
    return result


def _sanitize_table_name(name: str, target_type: str) -> str:
    """Makes a collection name safe for SQL table naming."""
    # Replace special characters with underscores
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    return safe.lower()


def _build_create_table(table_name: str, schema: dict, target_type: str) -> str:
    """Builds CREATE TABLE from inferred schema."""
    target = target_type.lower()
    
    col_defs = []
    for col_name, col_type in schema.items():
        if target == "mysql":
            col_defs.append(f"  `{col_name}` {col_type} NULL")
        elif target == "postgresql":
            col_defs.append(f'  "{col_name}" {col_type} NULL')
        else:
            col_defs.append(f"  [{col_name}] {col_type} NULL")
    
    cols_sql = ",\n".join(col_defs)
    
    if target == "mysql":
        return f"CREATE TABLE IF NOT EXISTS `{table_name}` (\n{cols_sql}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
    elif target == "postgresql":
        return f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n{cols_sql}\n);'
    else:
        return f"CREATE TABLE IF NOT EXISTS [{table_name}] (\n{cols_sql}\n);"


def _build_drop_table(table_name: str, target_type: str) -> str:
    """Builds DROP TABLE statement."""
    if target_type == "mysql":
        return f"DROP TABLE IF EXISTS `{table_name}`"
    elif target_type == "postgresql":
        return f'DROP TABLE IF EXISTS "{table_name}" CASCADE'
    else:
        return f"IF OBJECT_ID('{table_name}', 'U') IS NOT NULL DROP TABLE [{table_name}]"


def _insert_batch(engine: Engine, table_name: str, col_names: list, batch: list[dict], target_type: str):
    """Inserts a batch of rows into the SQL table."""
    if not batch:
        return
    
    target = target_type.lower()
    
    if target == "mysql":
        cols = ", ".join([f"`{c}`" for c in col_names])
        table_ref = f"`{table_name}`"
    elif target == "postgresql":
        cols = ", ".join([f'"{c}"' for c in col_names])
        table_ref = f'"{table_name}"'
    else:
        cols = ", ".join([f"[{c}]" for c in col_names])
        table_ref = f"[{table_name}]"
    
    params = ", ".join([f":col_{i}" for i in range(len(col_names))])
    insert_sql = f"INSERT INTO {table_ref} ({cols}) VALUES ({params})"
    
    rows_params = []
    for row in batch:
        param = {}
        for i, col in enumerate(col_names):
            val = row.get(col)
            param[f"col_{i}"] = _convert_mongo_value(val)
        rows_params.append(param)
    
    with engine.connect() as conn:
        conn.execute(text(insert_sql), rows_params)
        conn.commit()


def _flatten_document(doc: dict, prefix: str = "") -> dict:
    """
    Flattens a nested MongoDB document into a flat dictionary.
    Nested objects become parent_child keys.
    Arrays become JSON strings.
    """
    flat = {}
    for key, value in doc.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}_{key}"
        
        if key == "_id":
            flat["_id"] = str(value)
        elif isinstance(value, dict):
            flat.update(_flatten_document(value, full_key))
        elif isinstance(value, list):
            flat[full_key] = json.dumps(value, default=str)
        else:
            flat[full_key] = value
    
    return flat


def _convert_mongo_value(value):
    """Converts MongoDB values to SQL-compatible types."""
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return json.dumps(value, default=str)
    if isinstance(value, bytes):
        return value.hex()
    return value
