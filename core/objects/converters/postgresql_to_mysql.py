import re


def convert_postgresql_view_to_mysql(definition: str, schema_name: str, view_name: str) -> str:
    sql = definition.strip()

    sql = replace_postgres_casts(sql)
    sql = replace_double_quotes_with_backticks(sql)
    sql = replace_postgres_functions(sql)

    mysql_view_name = format_mysql_object_name(schema_name, view_name)

    sql = re.sub(
        r"CREATE\s+OR\s+REPLACE\s+VIEW\s+[`\"\w.]+",
        f"CREATE OR REPLACE VIEW `{mysql_view_name}`",
        sql,
        flags=re.IGNORECASE,
    )

    sql = re.sub(
        r"CREATE\s+VIEW\s+[`\"\w.]+",
        f"CREATE OR REPLACE VIEW `{mysql_view_name}`",
        sql,
        flags=re.IGNORECASE,
    )

    if not re.search(r"CREATE\s+OR\s+REPLACE\s+VIEW", sql, flags=re.IGNORECASE):
        sql = f"CREATE OR REPLACE VIEW `{mysql_view_name}` AS\n{sql}"

    return sql


def convert_postgresql_routine_to_mysql(definition: str, schema_name: str, routine_name: str) -> str:
    mysql_routine_name = format_mysql_object_name(schema_name, routine_name)

    safe_body = definition.replace("'", "''").replace("\\", "\\\\")

    return f"""
CREATE PROCEDURE `{mysql_routine_name}`()
BEGIN
    SELECT 'Original PostgreSQL routine preserved for manual review.' AS migration_note;
    SELECT '{safe_body[:2000]}' AS original_definition;
END
"""


def replace_double_quotes_with_backticks(sql: str) -> str:
    return re.sub(r'"([^"]+)"', r'`\1`', sql)


def replace_postgres_casts(sql: str) -> str:
    sql = re.sub(r"::\s*text", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"::\s*varchar", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"::\s*integer", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"::\s*numeric", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"::\s*timestamp", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"::\s*date", "", sql, flags=re.IGNORECASE)
    return sql


def replace_postgres_functions(sql: str) -> str:
    replacements = {
        "COALESCE": "IFNULL",
        "CURRENT_TIMESTAMP": "CURRENT_TIMESTAMP()",
        "LENGTH(": "CHAR_LENGTH(",
    }

    for old, new in replacements.items():
        sql = sql.replace(old, new)
        sql = sql.replace(old.lower(), new)

    return sql


def format_mysql_object_name(schema_name: str, object_name: str) -> str:
    return sanitize_mysql_identifier(f"{schema_name}_{object_name}")


def sanitize_mysql_identifier(identifier: str) -> str:
    return (
        str(identifier)
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )