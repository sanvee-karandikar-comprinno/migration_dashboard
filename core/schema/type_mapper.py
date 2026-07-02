"""
core/schema/type_mapper.py
==========================
Data type mapping between all supported SQL databases.

Supports all directions:
- MSSQL → MySQL, MSSQL → PostgreSQL
- MySQL → MSSQL, MySQL → PostgreSQL
- PostgreSQL → MSSQL, PostgreSQL → MySQL

WHY IS THIS NEEDED?
- Each database has its own data type names and sizes.
- VARCHAR(MAX) in MSSQL becomes LONGTEXT in MySQL and TEXT in PostgreSQL.
- This module translates types so the target schema is correct.
- All mappings are in dictionaries — nothing is hardcoded to a specific table.
"""


# =============================================================================
# MSSQL → MySQL type mappings
# =============================================================================
MSSQL_TO_MYSQL = {
    "bigint": "BIGINT",
    "binary": "BINARY",
    "bit": "TINYINT(1)",
    "char": "CHAR",
    "date": "DATE",
    "datetime": "DATETIME(3)",
    "datetime2": "DATETIME(6)",
    "datetimeoffset": "VARCHAR(50)",
    "decimal": "DECIMAL",
    "float": "DOUBLE",
    "image": "LONGBLOB",
    "int": "INT",
    "money": "DECIMAL(19,4)",
    "nchar": "CHAR",
    "ntext": "LONGTEXT",
    "numeric": "DECIMAL",
    "nvarchar": "VARCHAR",
    "real": "FLOAT",
    "smalldatetime": "DATETIME",
    "smallint": "SMALLINT",
    "smallmoney": "DECIMAL(10,4)",
    "text": "LONGTEXT",
    "time": "TIME(6)",
    "timestamp": "BINARY(8)",
    "tinyint": "TINYINT",
    "uniqueidentifier": "CHAR(36)",
    "varbinary": "LONGBLOB",
    "varchar": "VARCHAR",
    "xml": "LONGTEXT",
    "hierarchyid": "VARCHAR(255)",
    "geography": "LONGTEXT",
    "geometry": "LONGTEXT",
    "sql_variant": "LONGTEXT",
}

# =============================================================================
# MSSQL → PostgreSQL type mappings
# =============================================================================
MSSQL_TO_POSTGRESQL = {
    "bigint": "BIGINT",
    "binary": "BYTEA",
    "bit": "BOOLEAN",
    "char": "CHAR",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    "datetime2": "TIMESTAMP",
    "datetimeoffset": "TIMESTAMPTZ",
    "decimal": "NUMERIC",
    "float": "DOUBLE PRECISION",
    "image": "BYTEA",
    "int": "INTEGER",
    "money": "NUMERIC(19,4)",
    "nchar": "CHAR",
    "ntext": "TEXT",
    "numeric": "NUMERIC",
    "nvarchar": "VARCHAR",
    "real": "REAL",
    "smalldatetime": "TIMESTAMP",
    "smallint": "SMALLINT",
    "smallmoney": "NUMERIC(10,4)",
    "text": "TEXT",
    "time": "TIME",
    "timestamp": "BYTEA",
    "tinyint": "SMALLINT",
    "uniqueidentifier": "UUID",
    "varbinary": "BYTEA",
    "varchar": "VARCHAR",
    "xml": "XML",
    "hierarchyid": "TEXT",
    "geography": "TEXT",
    "geometry": "TEXT",
    "sql_variant": "TEXT",
}

# =============================================================================
# MySQL → PostgreSQL type mappings
# =============================================================================
MYSQL_TO_POSTGRESQL = {
    "bigint": "BIGINT",
    "binary": "BYTEA",
    "bit": "BOOLEAN",
    "blob": "BYTEA",
    "char": "CHAR",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    "decimal": "NUMERIC",
    "double": "DOUBLE PRECISION",
    "enum": "VARCHAR(255)",
    "float": "REAL",
    "int": "INTEGER",
    "integer": "INTEGER",
    "json": "JSONB",
    "longblob": "BYTEA",
    "longtext": "TEXT",
    "mediumblob": "BYTEA",
    "mediumint": "INTEGER",
    "mediumtext": "TEXT",
    "set": "VARCHAR(255)",
    "smallint": "SMALLINT",
    "text": "TEXT",
    "time": "TIME",
    "timestamp": "TIMESTAMP",
    "tinyblob": "BYTEA",
    "tinyint": "SMALLINT",
    "tinytext": "TEXT",
    "varbinary": "BYTEA",
    "varchar": "VARCHAR",
    "year": "INTEGER",
}

# =============================================================================
# MySQL → MSSQL type mappings
# =============================================================================
MYSQL_TO_MSSQL = {
    "bigint": "BIGINT",
    "binary": "BINARY",
    "bit": "BIT",
    "blob": "VARBINARY(MAX)",
    "char": "CHAR",
    "date": "DATE",
    "datetime": "DATETIME2",
    "decimal": "DECIMAL",
    "double": "FLOAT",
    "enum": "NVARCHAR(255)",
    "float": "REAL",
    "int": "INT",
    "integer": "INT",
    "json": "NVARCHAR(MAX)",
    "longblob": "VARBINARY(MAX)",
    "longtext": "NVARCHAR(MAX)",
    "mediumblob": "VARBINARY(MAX)",
    "mediumint": "INT",
    "mediumtext": "NVARCHAR(MAX)",
    "set": "NVARCHAR(255)",
    "smallint": "SMALLINT",
    "text": "NVARCHAR(MAX)",
    "time": "TIME",
    "timestamp": "DATETIME2",
    "tinyblob": "VARBINARY(MAX)",
    "tinyint": "TINYINT",
    "tinytext": "NVARCHAR(MAX)",
    "varbinary": "VARBINARY",
    "varchar": "NVARCHAR",
    "year": "INT",
}

# =============================================================================
# PostgreSQL → MySQL type mappings
# =============================================================================
POSTGRESQL_TO_MYSQL = {
    "bigint": "BIGINT",
    "bigserial": "BIGINT",
    "boolean": "TINYINT(1)",
    "bytea": "LONGBLOB",
    "char": "CHAR",
    "character": "CHAR",
    "character varying": "VARCHAR",
    "date": "DATE",
    "double precision": "DOUBLE",
    "integer": "INT",
    "int": "INT",
    "interval": "VARCHAR(50)",
    "json": "JSON",
    "jsonb": "JSON",
    "money": "DECIMAL(19,4)",
    "numeric": "DECIMAL",
    "real": "FLOAT",
    "serial": "INT",
    "smallint": "SMALLINT",
    "smallserial": "SMALLINT",
    "text": "LONGTEXT",
    "time": "TIME",
    "time without time zone": "TIME",
    "time with time zone": "TIME",
    "timestamp": "DATETIME(6)",
    "timestamp without time zone": "DATETIME(6)",
    "timestamp with time zone": "DATETIME(6)",
    "uuid": "CHAR(36)",
    "varchar": "VARCHAR",
    "xml": "LONGTEXT",
}

# =============================================================================
# PostgreSQL → MSSQL type mappings
# =============================================================================
POSTGRESQL_TO_MSSQL = {
    "bigint": "BIGINT",
    "bigserial": "BIGINT",
    "boolean": "BIT",
    "bytea": "VARBINARY(MAX)",
    "char": "CHAR",
    "character": "CHAR",
    "character varying": "NVARCHAR",
    "date": "DATE",
    "double precision": "FLOAT",
    "integer": "INT",
    "int": "INT",
    "interval": "NVARCHAR(50)",
    "json": "NVARCHAR(MAX)",
    "jsonb": "NVARCHAR(MAX)",
    "money": "MONEY",
    "numeric": "DECIMAL",
    "real": "REAL",
    "serial": "INT",
    "smallint": "SMALLINT",
    "smallserial": "SMALLINT",
    "text": "NVARCHAR(MAX)",
    "time": "TIME",
    "time without time zone": "TIME",
    "time with time zone": "TIME",
    "timestamp": "DATETIME2",
    "timestamp without time zone": "DATETIME2",
    "timestamp with time zone": "DATETIMEOFFSET",
    "uuid": "UNIQUEIDENTIFIER",
    "varchar": "NVARCHAR",
    "xml": "XML",
}


def get_type_map(source_type: str, target_type: str) -> dict:
    """
    Returns the appropriate type mapping dictionary for the given direction.
    
    Args:
        source_type: Source database type (mssql, mysql, postgresql)
        target_type: Target database type (mssql, mysql, postgresql)
        
    Returns:
        Dictionary mapping source types to target types
    """
    source = source_type.lower()
    target = target_type.lower()
    
    mapping_key = f"{source}_to_{target}"
    
    maps = {
        "mssql_to_mysql": MSSQL_TO_MYSQL,
        "mssql_to_postgresql": MSSQL_TO_POSTGRESQL,
        "mysql_to_postgresql": MYSQL_TO_POSTGRESQL,
        "mysql_to_mssql": MYSQL_TO_MSSQL,
        "postgresql_to_mysql": POSTGRESQL_TO_MYSQL,
        "postgresql_to_mssql": POSTGRESQL_TO_MSSQL,
    }
    
    if mapping_key in maps:
        return maps[mapping_key]
    
    # Same source and target — return identity mapping
    if source == target:
        return {}
    
    raise ValueError(f"No type mapping found for {source} → {target}")


def map_data_type(
    source_type: str,
    target_type: str,
    data_type: str,
    char_length=None,
    precision=None,
    scale=None,
) -> str:
    """
    Maps a single column data type from source to target database.
    
    Args:
        source_type: Source database type (e.g., 'mssql')
        target_type: Target database type (e.g., 'mysql')
        data_type: The source column data type (e.g., 'nvarchar')
        char_length: Character max length (e.g., 255, -1 for MAX)
        precision: Numeric precision
        scale: Numeric scale
        
    Returns:
        Target data type string (e.g., 'VARCHAR(255)')
    """
    type_map = get_type_map(source_type, target_type)
    dt_lower = data_type.lower().strip()
    
    # If same database type, return as-is
    if source_type.lower() == target_type.lower():
        return data_type
    
    # Look up base type in the mapping dictionary
    base_target_type = type_map.get(dt_lower, "TEXT")
    
    # Handle sized string types (varchar, nvarchar, char, nchar)
    if dt_lower in ("varchar", "nvarchar", "character varying"):
        if char_length is None or char_length == -1:
            # MAX length
            if target_type.lower() == "mysql":
                return "LONGTEXT"
            elif target_type.lower() == "postgresql":
                return "TEXT"
            else:
                return "NVARCHAR(MAX)"
        else:
            length = min(int(char_length), 16383) if target_type.lower() == "mysql" else int(char_length)
            return f"{base_target_type}({length})"
    
    if dt_lower in ("char", "nchar", "character"):
        if char_length and int(char_length) > 0:
            length = min(int(char_length), 255)
            return f"{base_target_type}({length})"
        return base_target_type
    
    # Handle precision numeric types (decimal, numeric)
    if dt_lower in ("decimal", "numeric"):
        if precision and scale is not None:
            return f"{base_target_type}({precision},{scale})"
        elif precision:
            return f"{base_target_type}({precision})"
        return base_target_type
    
    # Handle binary with size
    if dt_lower in ("varbinary", "binary"):
        if char_length is None or char_length == -1:
            return base_target_type  # Use default (LONGBLOB, BYTEA, VARBINARY(MAX))
        if target_type.lower() == "mysql" and dt_lower == "binary":
            return f"BINARY({min(int(char_length), 255)})"
        return base_target_type
    
    return base_target_type
