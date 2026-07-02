"""
core/nosql/sql_to_mongo_migrator.py
===================================
Migrates data from a SQL database (MSSQL/MySQL/PostgreSQL) into MongoDB.

Each SQL table becomes a MongoDB collection.
Each row becomes a document.
Handles type conversion (Decimal → float, bytes → Binary, etc.)
"""

import logging
from decimal import Decimal
from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine
from pymongo import MongoClient

logger = logging.getLogger(__name__)

# MSSQL types that cannot be read directly via ODBC
CAST_REQUIRED_TYPES = {"xml", "hierarchyid", "geography", "geometry", "sql_variant"}


def migrate_sql_to_mongodb(
    source_engine: Engine,
    mongo_client: MongoClient,
    source_type: str,
    source_database: str,
    target_database: str,
    audit_report: dict,
    batch_size: int = 1000,
    log_callback=None,
) -> dict:
    """
    Migrates all SQL tables to MongoDB collections.
    
    Args:
        source_engine: SQLAlchemy engine for source SQL database
        mongo_client: Connected MongoClient
        source_type: Source DB type ('mssql', 'mysql', 'postgresql')
        source_database: Source database name
        target_database: Target MongoDB database name
        audit_report: Audit report from DynamicAuditor
        batch_size: Documents per batch insert
        log_callback: Optional progress callback
        
    Returns:
        Migration result dictionary
    """
    target_db = mongo_client[target_database]
    tables = audit_report.get("tables", [])
    columns = audit_report.get("columns", [])
    
    # Group columns by table
    columns_by_table = {}
    for col in columns:
        key = (col["schema_name"], col["table_name"])
        if key not in columns_by_table:
            columns_by_table[key] = []
        columns_by_table[key].append(col)
    
    result = {
        "status": "completed",
        "tables_migrated": 0,
        "tables_failed": 0,
        "total_documents": 0,
        "table_results": [],
    }
    
    for table in tables:
        schema_name = table["schema_name"]
        table_name = table["table_name"]
        key = (schema_name, table_name)
        table_cols = columns_by_table.get(key, [])
        
        msg = f"Migrating to MongoDB: {schema_name}.{table_name}"
        logger.info(msg)
        if log_callback:
            log_callback(msg)
        
        try:
            # Collection name follows convention: schema_tablename
            from core.schema.schema_builder import get_collection_name
            collection_name = get_collection_name(schema_name, table_name)
            collection = target_db[collection_name]
            
            # Drop existing collection for clean migration
            collection.drop()
            
            # Build SELECT query
            select_sql = _build_select(schema_name, table_name, table_cols, source_type)
            
            docs_inserted = 0
            with source_engine.connect() as conn:
                rows = conn.execute(text(select_sql))
                col_names = [c["column_name"] for c in sorted(table_cols, key=lambda x: x.get("ordinal_position", 0))]
                
                batch = []
                for row in rows:
                    doc = {}
                    for i, col_name in enumerate(col_names):
                        doc[col_name] = _convert_value(row[i])
                    batch.append(doc)
                    
                    if len(batch) >= batch_size:
                        collection.insert_many(batch)
                        docs_inserted += len(batch)
                        batch = []
                
                # Insert remaining
                if batch:
                    collection.insert_many(batch)
                    docs_inserted += len(batch)
            
            result["tables_migrated"] += 1
            result["total_documents"] += docs_inserted
            result["table_results"].append({
                "table_name": f"{schema_name}.{table_name}",
                "collection_name": collection_name,
                "status": "success",
                "documents": docs_inserted,
                "error": None,
            })
            
        except Exception as e:
            result["tables_failed"] += 1
            result["table_results"].append({
                "table_name": f"{schema_name}.{table_name}",
                "collection_name": "",
                "status": "failed",
                "documents": 0,
                "error": str(e),
            })
            logger.error(f"Failed: {schema_name}.{table_name}: {e}")
    
    if result["tables_failed"] > 0:
        result["status"] = "completed_with_errors"
    
    return result


def _build_select(schema_name: str, table_name: str, columns: list[dict], source_type: str) -> str:
    """Builds SELECT statement with CAST for special types."""
    col_exprs = []
    for col in sorted(columns, key=lambda c: c.get("ordinal_position", 0)):
        col_name = col["column_name"]
        data_type = col["data_type"].lower()
        
        if source_type == "mssql":
            if data_type in CAST_REQUIRED_TYPES:
                col_exprs.append(f"CAST([{col_name}] AS NVARCHAR(MAX)) AS [{col_name}]")
            elif data_type in ("varbinary", "image", "binary"):
                col_exprs.append(f"CONVERT(VARCHAR(MAX), [{col_name}], 2) AS [{col_name}]")
            else:
                col_exprs.append(f"[{col_name}]")
        elif source_type == "mysql":
            col_exprs.append(f"`{col_name}`")
        else:
            col_exprs.append(f'"{col_name}"')
    
    if source_type == "mssql":
        return f"SELECT {', '.join(col_exprs)} FROM [{schema_name}].[{table_name}]"
    elif source_type == "mysql":
        return f"SELECT {', '.join(col_exprs)} FROM `{table_name}`"
    else:
        return f'SELECT {", ".join(col_exprs)} FROM "{schema_name}"."{table_name}"'


def _convert_value(value):
    """Converts Python values to MongoDB-compatible types."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat() if isinstance(value, date) and not isinstance(value, datetime) else value
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value
