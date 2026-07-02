import re


def convert_mysql_view_to_postgresql(definition: str, schema_name: str, view_name: str) -> str:
    sql = definition.strip()

    sql = remove_mysql_options(sql)
    sql = replace_backticks_with_double_quotes(sql)
    sql = replace_mysql_functions(sql)

    sql = re.sub(
        r"CREATE\s+(?:ALGORITHM\s*=\s*\w+\s+)?(?:DEFINER\s*=\s*[^ ]+\s+)?(?:SQL\s+SECURITY\s+\w+\s+)?VIEW\s+[\w`\".]+",
        f'CREATE OR REPLACE VIEW "{schema_name}"."{view_name}"',
        sql,
        flags=re.IGNORECASE,
    )

    if not re.search(r"CREATE\s+OR\s+REPLACE\s+VIEW", sql, flags=re.IGNORECASE):
        sql = f'CREATE OR REPLACE VIEW "{schema_name}"."{view_name}" AS\n{sql}'

    return sql


def convert_mysql_routine_to_postgresql(definition: str, schema_name: str, routine_name: str) -> str:
    safe_body = definition.replace("'", "''").replace("%", "%%")

    return f"""
CREATE OR REPLACE PROCEDURE "{schema_name}"."{routine_name}"()
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE '%', 'Original MySQL routine preserved for review.';
    RAISE NOTICE '%', '{safe_body[:2500]}';
END;
$$;
"""


def remove_mysql_options(sql: str) -> str:
    sql = re.sub(r"DEFINER\s*=\s*`?[^`\s]+`?@`?[^`\s]+`?", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"ALGORITHM\s*=\s*\w+", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"SQL\s+SECURITY\s+\w+", "", sql, flags=re.IGNORECASE)
    return sql


def replace_backticks_with_double_quotes(sql: str) -> str:
    return re.sub(r"`([^`]+)`", r'"\1"', sql)


def replace_mysql_functions(sql: str) -> str:
    replacements = {
        "IFNULL": "COALESCE",
        "NOW()": "CURRENT_TIMESTAMP",
        "CURRENT_TIMESTAMP()": "CURRENT_TIMESTAMP",
        "CHAR_LENGTH(": "LENGTH(",
    }

    for old, new in replacements.items():
        sql = sql.replace(old, new)
        sql = sql.replace(old.lower(), new)

    return sql