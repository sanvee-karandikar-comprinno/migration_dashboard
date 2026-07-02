"""
core/data/data_migrator.py
==========================
Migrates data from source to target database in batches.
Handles ALL tables — nothing gets skipped unless it truly has zero columns.
Uses raw SQL with proper escaping for maximum compatibility.
"""

import logging
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# MSSQL types that need CAST to be readable via ODBC
CAST_REQUIRED_TYPES = {"xml", "hierarchyid", "geography", "geometry", "sql_variant"}
BINARY_TYPES = {"varbinary", "image", "binary", "timestamp"}


def migrate_data(
    source_engine: Engine,
    target_engine: Engine,
    source_type: str,
    target_type: str,
    audit_report: dict,
    batch_size: int = 1000,
    log_callback=None,
) -> dict:
    """
    Migrates all table data from source to target in batches.
    Every table in the audit is attempted — nothing is skipped.
    """
    if target_type.lower() == "mongodb":
        return {"status": "skipped", "message": "Use SQL-to-MongoDB migrator.",
                "tables_migrated": 0, "tables_failed": 0, "total_rows": 0, "table_results": []}

    tables = audit_report.get("tables", [])
    columns = audit_report.get("columns", [])

    # Group columns by (schema, table) — case-insensitive matching
    columns_by_table = {}
    for col in columns:
        key = (col["schema_name"].lower(), col["table_name"].lower())
        if key not in columns_by_table:
            columns_by_table[key] = []
        columns_by_table[key].append(col)

    result = {"status": "completed", "tables_migrated": 0, "tables_failed": 0,
              "total_rows": 0, "table_results": []}

    # Disable FK checks on target before loading data
    _disable_constraints(target_engine, target_type)

    for table in tables:
        schema_name = table["schema_name"]
        table_name = table["table_name"]
        key = (schema_name.lower(), table_name.lower())
        table_cols = columns_by_table.get(key, [])

        if not table_cols:
            # Still record it — don't silently skip
            result["table_results"].append({
                "table_name": f"{schema_name}.{table_name}",
                "status": "failed", "rows_migrated": 0,
                "error": "No column metadata found for this table"})
            result["tables_failed"] += 1
            continue

        if log_callback:
            log_callback(f"Migrating: {schema_name}.{table_name}")

        table_result = _migrate_single_table(
            source_engine, target_engine, source_type, target_type,
            schema_name, table_name, table_cols, batch_size)

        result["table_results"].append(table_result)
        if table_result["status"] == "success":
            result["tables_migrated"] += 1
            result["total_rows"] += table_result["rows_migrated"]
        else:
            result["tables_failed"] += 1

    # Re-enable FK checks
    _enable_constraints(target_engine, target_type)

    if result["tables_failed"] > 0:
        result["status"] = "completed_with_errors"
    return result


def _disable_constraints(engine: Engine, target_type: str):
    """Disable foreign key checks for bulk loading."""
    try:
        with engine.connect() as conn:
            if target_type.lower() == "mysql":
                conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                conn.commit()
            elif target_type.lower() == "postgresql":
                # PostgreSQL: defer constraints
                conn.execute(text("SET session_replication_role = 'replica'"))
                conn.commit()
    except Exception:
        pass


def _enable_constraints(engine: Engine, target_type: str):
    """Re-enable foreign key checks after bulk loading."""
    try:
        with engine.connect() as conn:
            if target_type.lower() == "mysql":
                conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
                conn.commit()
            elif target_type.lower() == "postgresql":
                conn.execute(text("SET session_replication_role = 'origin'"))
                conn.commit()
    except Exception:
        pass


def _migrate_single_table(source_engine, target_engine, source_type, target_type,
                          schema_name, table_name, columns, batch_size) -> dict:
    """Migrates one table: SELECT from source, INSERT into target in batches."""
    try:
        sorted_cols = sorted(columns, key=lambda c: c.get("ordinal_position", 0))
        select_sql = _build_select(schema_name, table_name, sorted_cols, source_type)
        insert_sql = _build_insert(schema_name, table_name, sorted_cols, target_type)

        rows_migrated = 0
        with source_engine.connect() as src_conn:
            result_proxy = src_conn.execute(text(select_sql))

            while True:
                batch = result_proxy.fetchmany(batch_size)
                if not batch:
                    break

                # Convert to list of param dicts
                params_list = []
                for row in batch:
                    params = {}
                    for i, val in enumerate(row):
                        # Handle None and special types
                        if val is None:
                            params[f"p{i}"] = None
                        elif isinstance(val, bytes):
                            params[f"p{i}"] = val.hex() if target_type.lower() == "mysql" else val
                        else:
                            params[f"p{i}"] = val
                    params_list.append(params)

                # Insert batch
                with target_engine.connect() as tgt_conn:
                    tgt_conn.execute(text(insert_sql), params_list)
                    tgt_conn.commit()

                rows_migrated += len(batch)

        return {"table_name": f"{schema_name}.{table_name}", "status": "success",
                "rows_migrated": rows_migrated, "error": None}

    except Exception as e:
        return {"table_name": f"{schema_name}.{table_name}", "status": "failed",
                "rows_migrated": 0, "error": str(e)[:300]}


def _build_select(schema_name, table_name, columns, source_type):
    """Builds SELECT with CAST for problematic types."""
    source = source_type.lower()
    col_exprs = []

    for col in columns:
        name = col["column_name"]
        dtype = col["data_type"].lower() if col["data_type"] else ""

        if source == "mssql":
            if dtype in CAST_REQUIRED_TYPES:
                col_exprs.append(f"CAST([{name}] AS NVARCHAR(MAX)) AS [{name}]")
            elif dtype in BINARY_TYPES:
                col_exprs.append(f"CONVERT(VARCHAR(MAX), [{name}], 2) AS [{name}]")
            else:
                col_exprs.append(f"[{name}]")
        elif source == "mysql":
            col_exprs.append(f"`{name}`")
        else:
            col_exprs.append(f'"{name}"')

    if source == "mssql":
        from_ref = f"[{schema_name}].[{table_name}]"
    elif source == "mysql":
        from_ref = f"`{table_name}`"
    else:
        from_ref = f'"{schema_name}"."{table_name}"'

    return f"SELECT {', '.join(col_exprs)} FROM {from_ref}"


def _build_insert(schema_name, table_name, columns, target_type):
    """Builds INSERT with named parameters :p0, :p1, etc.
    Uses same naming convention as schema_builder:
    - PostgreSQL: "schema"."table"
    - MySQL: `schema_table`
    - MSSQL: [schema].[table]
    """
    from core.schema.schema_builder import get_qualified_table_name, quote_identifier
    target = target_type.lower()

    table_ref = get_qualified_table_name(schema_name, table_name, target)
    cols = ", ".join([quote_identifier(c['column_name'], target) for c in columns])
    params = ", ".join([f":p{i}" for i in range(len(columns))])
    return f"INSERT INTO {table_ref} ({cols}) VALUES ({params})"
