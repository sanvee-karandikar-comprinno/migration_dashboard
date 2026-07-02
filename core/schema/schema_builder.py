"""
core/schema/schema_builder.py
=============================
Generates CREATE TABLE DDL statements from audit metadata.

Naming conventions per target:
- PostgreSQL: Preserves schemas → "humanresources"."employee" (CREATE SCHEMA used)
- MySQL: Flat namespace → `humanresources_employee` (schema prefixed to table name)
- MSSQL: Native schemas → [HumanResources].[Employee] (CREATE SCHEMA used)
- MongoDB: Flat namespace → humanresources_employee (collection name)
"""

from core.schema.type_mapper import map_data_type


def build_schema_ddl(audit_report: dict, source_type: str, target_type: str) -> dict:
    """
    Main entry point: builds all DDL statements needed for the target database.

    Returns dict with schema_statements, table_statements, total_tables.
    """
    target = target_type.lower()

    if target == "mongodb":
        return {
            "schema_statements": [],
            "table_statements": [],
            "total_tables": 0,
            "message": "MongoDB is schemaless — collections are created during data migration.",
        }

    schema_stmts = _build_schema_namespaces(audit_report, target)
    table_stmts = _build_table_statements(audit_report, source_type, target)

    return {
        "schema_statements": schema_stmts,
        "table_statements": table_stmts,
        "total_tables": len(table_stmts),
    }


def _build_schema_namespaces(audit_report: dict, target_type: str) -> list[str]:
    """
    Generates CREATE SCHEMA statements.
    - PostgreSQL: Creates actual schemas (humanresources, production, etc.)
    - MSSQL: Creates actual schemas
    - MySQL: Not needed (schemas become table name prefixes)
    """
    if target_type == "mysql":
        return []

    schemas = set()
    for table in audit_report.get("tables", []):
        schema_name = table.get("schema_name", "")
        if schema_name:
            s = schema_name.lower()
            # Skip default schemas that already exist
            if target_type == "postgresql" and s in ("public",):
                continue
            if target_type == "mssql" and s in ("dbo",):
                continue
            schemas.add(s)

    if target_type == "postgresql":
        return [f'CREATE SCHEMA IF NOT EXISTS "{s}";' for s in sorted(schemas)]
    elif target_type == "mssql":
        # MSSQL needs IF NOT EXISTS check via dynamic SQL
        stmts = []
        for s in sorted(schemas):
            stmts.append(
                f"IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = '{s}') "
                f"EXEC('CREATE SCHEMA [{s}]');"
            )
        return stmts
    return []


def _build_table_statements(audit_report: dict, source_type: str, target_type: str) -> list[dict]:
    """Generates CREATE TABLE statements for each table."""
    tables = audit_report.get("tables", [])
    columns = audit_report.get("columns", [])
    primary_keys = audit_report.get("primary_keys", [])

    # Group columns by (schema, table)
    columns_by_table = {}
    for col in columns:
        key = (col["schema_name"], col["table_name"])
        if key not in columns_by_table:
            columns_by_table[key] = []
        columns_by_table[key].append(col)

    # Group PKs by table
    pks_by_table = {}
    for pk in primary_keys:
        key = (pk["schema_name"], pk["table_name"])
        if key not in pks_by_table:
            pks_by_table[key] = []
        pks_by_table[key].append(pk["column_name"])

    results = []
    for table in tables:
        schema_name = table["schema_name"]
        table_name = table["table_name"]
        key = (schema_name, table_name)

        table_columns = columns_by_table.get(key, [])
        table_pks = pks_by_table.get(key, [])

        if not table_columns:
            continue

        ddl = _generate_create_table(
            schema_name, table_name, table_columns, table_pks,
            source_type, target_type
        )

        results.append({
            "schema_name": schema_name,
            "table_name": table_name,
            "ddl": ddl,
            "columns_count": len(table_columns),
        })

    return results


def _generate_create_table(schema_name, table_name, columns, primary_keys, source_type, target_type):
    """Generates a single CREATE TABLE statement with proper naming."""
    target = target_type.lower()
    table_ref = get_qualified_table_name(schema_name, table_name, target)

    col_defs = []
    for col in sorted(columns, key=lambda c: c.get("ordinal_position", 0)):
        col_def = _build_column_def(col, source_type, target_type)
        col_defs.append(col_def)

    if primary_keys:
        pk_cols = ", ".join([quote_identifier(c, target) for c in primary_keys])
        col_defs.append(f"  PRIMARY KEY ({pk_cols})")

    cols_sql = ",\n".join(col_defs)

    if target == "mysql":
        return f"CREATE TABLE IF NOT EXISTS {table_ref} (\n{cols_sql}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
    else:
        return f"CREATE TABLE IF NOT EXISTS {table_ref} (\n{cols_sql}\n);"


def _build_column_def(col: dict, source_type: str, target_type: str) -> str:
    """Builds a single column definition line."""
    target = target_type.lower()
    col_name = quote_identifier(col["column_name"], target)

    mapped_type = map_data_type(
        source_type=source_type,
        target_type=target_type,
        data_type=col["data_type"],
        char_length=col.get("character_maximum_length"),
        precision=col.get("numeric_precision"),
        scale=col.get("numeric_scale"),
    )

    nullable = "NULL" if col.get("is_nullable", "YES") == "YES" else "NOT NULL"
    return f"  {col_name} {mapped_type} {nullable}"


# =============================================================================
# PUBLIC HELPERS — Used by data_migrator and object_migrator too
# =============================================================================

def get_qualified_table_name(schema_name: str, table_name: str, target_type: str) -> str:
    """
    Returns the fully qualified table name for the target database.

    Naming conventions:
    - PostgreSQL: "schema_name"."table_name"  (real schemas)
    - MySQL: `schemaname_tablename`  (flat, schema becomes prefix)
    - MSSQL: [schema_name].[table_name]  (real schemas)
    - MongoDB: schemaname_tablename  (collection name, flat)
    """
    target = target_type.lower()
    schema = schema_name.lower() if schema_name else ""
    tbl = table_name.lower()

    if target == "postgresql":
        # PostgreSQL supports real schemas — use schema.table
        s = schema if schema and schema != "dbo" else "public"
        return f'"{s}"."{tbl}"'

    elif target == "mysql":
        # MySQL has no schemas inside a database — flatten: schema_table
        if schema and schema not in ("dbo", "public"):
            return f"`{schema}_{tbl}`"
        else:
            return f"`{tbl}`"

    elif target == "mssql":
        # MSSQL supports real schemas
        s = schema if schema else "dbo"
        return f"[{s}].[{tbl}]"

    elif target == "mongodb":
        # MongoDB collections are flat — use schema_table
        if schema and schema not in ("dbo", "public"):
            return f"{schema}_{tbl}"
        else:
            return tbl

    return f"`{tbl}`"


def get_collection_name(schema_name: str, table_name: str) -> str:
    """Returns MongoDB collection name from schema + table."""
    schema = schema_name.lower() if schema_name else ""
    tbl = table_name.lower()
    if schema and schema not in ("dbo", "public"):
        return f"{schema}_{tbl}"
    return tbl


def quote_identifier(name: str, target_type: str) -> str:
    """Quotes a single identifier (column name)."""
    target = target_type.lower()
    n = name.lower()
    if target == "mysql":
        return f"`{n}`"
    elif target == "postgresql":
        return f'"{n}"'
    else:
        return f"[{n}]"
