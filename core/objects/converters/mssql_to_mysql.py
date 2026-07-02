import re


def convert_mssql_view_to_mysql(definition: str, schema_name: str, view_name: str) -> str:
    sql = definition.strip()

    sql = remove_sql_server_options(sql)

    mysql_view_name = format_mysql_object_name(schema_name, view_name)

    # Normalize brackets only for detecting XML/PIVOT and extracting output columns.
    # Do this BEFORE schema.table replacement, because XML calls like Column.value()
    # must not become fake function names like Column_value().
    detection_sql = replace_square_brackets(sql)

    if contains_sqlserver_xml_methods(detection_sql):
        return create_mysql_compatibility_view(
            view_name=mysql_view_name,
            sql=detection_sql,
            reason="SQL Server XML methods detected. XML columns are migrated as TEXT, but XML view logic needs manual rewrite."
        )

    if "PIVOT" in detection_sql.upper():
        return create_mysql_compatibility_view(
            view_name=mysql_view_name,
            sql=detection_sql,
            reason="SQL Server PIVOT detected. MySQL requires CASE aggregation rewrite."
        )

    sql = replace_schema_table_references(sql)
    sql = replace_square_brackets(sql)
    sql = replace_schema_table_references(sql)

    sql = remove_schema_binding(sql)
    sql = replace_sql_server_functions(sql)
    sql = convert_mssql_alias_assignment(sql)
    sql = quote_alias_column_references(sql)

    sql = re.sub(
        r"CREATE\s+VIEW\s+[`\"\w\.\[\]]+",
        f"CREATE OR REPLACE VIEW `{mysql_view_name}`",
        sql,
        flags=re.IGNORECASE,
    )

    return sql


def convert_mssql_routine_to_mysql(definition: str, schema_name: str, routine_name: str) -> str:
    mysql_routine_name = format_mysql_object_name(schema_name, routine_name)

    safe_body = (
        definition
        .replace("'", "''")
        .replace("\\", "\\\\")
    )

    return f"""
CREATE PROCEDURE `{mysql_routine_name}`()
BEGIN
    SELECT 'Original MSSQL routine preserved for manual review.' AS migration_note;
    SELECT '{safe_body[:2000]}' AS original_definition;
END
"""


def create_mysql_compatibility_view(view_name: str, sql: str, reason: str) -> str:
    columns = extract_view_output_columns(sql)

    if not columns:
        columns = ["migration_note"]

    select_items = [
        f"CAST(NULL AS CHAR(255)) AS `{column}`"
        for column in columns
    ]

    select_items.append(f"'{reason.replace(chr(39), chr(39) * 2)}' AS `migration_note`")

    return f"""
CREATE OR REPLACE VIEW `{view_name}` AS
SELECT
    {",\n    ".join(select_items)}
"""


def extract_view_output_columns(sql: str) -> list[str]:
    columns = []

    for match in re.finditer(r'\s+AS\s+`([^`]+)`', sql, flags=re.IGNORECASE):
        columns.append(match.group(1))

    for match in re.finditer(r'\s+AS\s+"([^"]+)"', sql, flags=re.IGNORECASE):
        columns.append(match.group(1))

    for match in re.finditer(r'\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)', sql, flags=re.IGNORECASE):
        columns.append(match.group(1))

    seen = set()
    final_columns = []

    for column in columns:
        safe = sanitize_mysql_identifier(column)

        if safe and safe not in seen:
            seen.add(safe)
            final_columns.append(safe)

    return final_columns[:100]


def remove_sql_server_options(sql: str) -> str:
    sql = re.sub(r"SET\s+ANSI_NULLS\s+ON\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"SET\s+QUOTED_IDENTIFIER\s+ON\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bGO\b", "", sql, flags=re.IGNORECASE)
    return sql


def replace_schema_table_references(sql: str) -> str:
    """
    Generic conversion of SQL Server schema.table references into MySQL flat table names.

    Converts:
        [Schema].[Table]
        "Schema"."Table"
        `Schema`.`Table`
        [Schema].Table
        "Schema".Table
        `Schema`.Table

    Into:
        `Schema_Table`
    """

    pattern = re.compile(
        r"""
        (?P<schema>
            \[[A-Za-z_][A-Za-z0-9_]*\] |
            "[A-Za-z_][A-Za-z0-9_]*" |
            `[A-Za-z_][A-Za-z0-9_]*`
        )
        \s*\.\s*
        (?P<table>
            \[[A-Za-z_][A-Za-z0-9_]*\] |
            "[A-Za-z_][A-Za-z0-9_]*" |
            `[A-Za-z_][A-Za-z0-9_]*` |
            [A-Za-z_][A-Za-z0-9_]*
        )
        """,
        re.VERBOSE,
    )

    def clean_identifier(value: str) -> str:
        return value.strip().strip("[]`\"")

    def replace_match(match):
        schema_name = clean_identifier(match.group("schema"))
        table_name = clean_identifier(match.group("table"))
        return f"`{sanitize_mysql_identifier(schema_name + '_' + table_name)}`"

    return pattern.sub(replace_match, sql)

def replace_square_brackets(sql: str) -> str:
    return re.sub(
        r"\[([A-Za-z_][A-Za-z0-9_ ]*)\]",
        lambda m: f"`{sanitize_mysql_identifier(m.group(1))}`",
        sql,
    )


def remove_schema_binding(sql: str) -> str:
    return re.sub(
        r"\s+WITH\s+SCHEMABINDING\s+",
        "\n",
        sql,
        flags=re.IGNORECASE,
    )


def replace_sql_server_functions(sql: str) -> str:
    replacements = {
        "ISNULL": "IFNULL",
        "GETDATE()": "CURRENT_TIMESTAMP()",
        "LEN(": "CHAR_LENGTH(",
    }

    for old, new in replacements.items():
        sql = sql.replace(old, new)
        sql = sql.replace(old.lower(), new)

    return sql


def convert_mssql_alias_assignment(sql: str) -> str:
    pattern = r',\s*`([^`]+)`\s*=\s*([a-zA-Z_][\w]*)\.`([^`]+)`'
    sql = re.sub(pattern, r',\n    \2.`\3` AS `\1`', sql)

    pattern_2 = r',\s*`([^`]+)`\s*=\s*([a-zA-Z_][\w]*)\.([A-Za-z_][A-Za-z0-9_]*)'
    sql = re.sub(pattern_2, r',\n    \2.`\3` AS `\1`', sql)

    return sql


def quote_alias_column_references(sql: str) -> str:
    aliases = extract_table_aliases(sql)

    for alias in aliases:
        sql = re.sub(
            rf'\b{re.escape(alias)}\.([A-Za-z_][A-Za-z0-9_]*)\b',
            rf'{alias}.`\1`',
            sql,
        )

    return sql


def extract_table_aliases(sql: str) -> set[str]:
    aliases = set()

    patterns = [
        r'\bFROM\s+`[^`]+`\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bJOIN\s+`[^`]+`\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bINNER\s+JOIN\s+`[^`]+`\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bLEFT\s+OUTER\s+JOIN\s+`[^`]+`\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bLEFT\s+JOIN\s+`[^`]+`\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bRIGHT\s+JOIN\s+`[^`]+`\s+([A-Za-z_][A-Za-z0-9_]*)',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, sql, flags=re.IGNORECASE):
            alias = match.group(1)
            if alias.upper() not in {"ON", "WHERE", "JOIN", "INNER", "LEFT", "RIGHT"}:
                aliases.add(alias)

    return aliases


def contains_sqlserver_xml_methods(sql: str) -> bool:
    return bool(
        re.search(
            r'(\.nodes\s*\(|\.value\s*\(|\.`nodes`\s*\(|\.`value`\s*\(|\bCROSS\s+APPLY\b|\bOUTER\s+APPLY\b)',
            sql,
            re.IGNORECASE,
        )
    )


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