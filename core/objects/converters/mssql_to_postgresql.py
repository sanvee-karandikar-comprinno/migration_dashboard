import re


def convert_mssql_view_to_postgresql(definition: str, schema_name: str, view_name: str) -> str:
    sql = definition.strip()

    sql = remove_sql_server_options(sql)
    sql = replace_square_brackets(sql)
    sql = remove_schema_binding(sql)
    sql = replace_sql_server_functions(sql)
    sql = convert_mssql_alias_assignment(sql)
    sql = quote_schema_table_references(sql)
    sql = quote_alias_column_references(sql)
    sql = convert_simple_string_concat(sql)

    if contains_sqlserver_xml_methods(sql):
        return create_compatibility_view(
        schema_name=schema_name,
        view_name=view_name,
        sql=sql,
        reason="XML columns were migrated as TEXT. SQL Server XML methods require manual XPath rewrite."
    )

    if "PIVOT" in sql.upper():
        try:
            converted_body = convert_simple_pivot_to_case(sql)
            return f'''
            CREATE OR REPLACE VIEW "{schema_name}"."{view_name}" AS
            {converted_body};
            '''
        except Exception:
            return create_compatibility_view(
                schema_name=schema_name,
                view_name=view_name,
                sql=sql,
                reason="PIVOT was detected but is too complex for automatic CASE aggregation conversion."
            )

    sql = re.sub(
        r"CREATE\s+VIEW\s+[\w\[\]\"\.]+",
        f'CREATE OR REPLACE VIEW "{schema_name}"."{view_name}"',
        sql,
        flags=re.IGNORECASE,
    )

    return sql


def convert_mssql_routine_to_postgresql(definition: str, schema_name: str, routine_name: str) -> str:
    sql = definition.strip()
    sql = remove_sql_server_options(sql)
    sql = replace_square_brackets(sql)

    safe_body = sql.replace("'", "''").replace("%", "%%")

    return f'''
CREATE OR REPLACE PROCEDURE "{schema_name}"."{routine_name}"()
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE '%', 'Original MSSQL routine preserved for review.';
    RAISE NOTICE '%', '{safe_body[:2500]}';
END;
$$;
'''


def create_compatibility_view(schema_name: str, view_name: str, sql: str, reason: str) -> str:
    columns = extract_view_output_columns(sql)

    if not columns:
        columns = ["migration_note"]

    select_items = [
        f"NULL::text AS \"{column}\""
        for column in columns
    ]

    select_items.append(f"'{reason.replace(chr(39), chr(39) * 2)}'::text AS migration_note")

    return f'''
CREATE OR REPLACE VIEW "{schema_name}"."{view_name}" AS
SELECT
    {",\n    ".join(select_items)};
'''


def extract_view_output_columns(sql: str) -> list[str]:
    aliases = []

    for match in re.finditer(r'\s+AS\s+"([^"]+)"', sql, flags=re.IGNORECASE):
        aliases.append(match.group(1))

    for match in re.finditer(r'\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)', sql, flags=re.IGNORECASE):
        aliases.append(match.group(1))

    simple_columns = re.findall(r'[,|\s]"([A-Za-z_][A-Za-z0-9_]*)"', sql)

    for column in simple_columns:
        if column not in aliases and column.lower() not in {
            "select", "from", "where", "join", "inner", "left", "right", "on"
        }:
            aliases.append(column)

    seen = set()
    final_columns = []

    for column in aliases:
        safe = column.replace('"', '').strip()

        if safe and safe not in seen:
            seen.add(safe)
            final_columns.append(safe)

    return final_columns[:100]


def remove_sql_server_options(sql: str) -> str:
    sql = re.sub(r"SET\s+ANSI_NULLS\s+ON\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"SET\s+QUOTED_IDENTIFIER\s+ON\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bGO\b", "", sql, flags=re.IGNORECASE)
    return sql


def replace_square_brackets(sql: str) -> str:
    return re.sub(
        r"\[([A-Za-z_][A-Za-z0-9_ ]*)\]",
        lambda match: f'"{match.group(1)}"',
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
        "ISNULL": "COALESCE",
        "GETDATE()": "CURRENT_TIMESTAMP",
        "LEN(": "LENGTH(",
        "LTRIM(RTRIM(": "TRIM(",
    }

    for old, new in replacements.items():
        sql = sql.replace(old, new)
        sql = sql.replace(old.lower(), new)

    return sql


def convert_mssql_alias_assignment(sql: str) -> str:
    pattern = r',\s*"([^"]+)"\s*=\s*([a-zA-Z_][\w]*)\."([^"]+)"'
    sql = re.sub(pattern, r',\n    \2."\3" AS "\1"', sql)

    pattern_2 = r',\s*"([^"]+)"\s*=\s*([a-zA-Z_][\w]*)\.([A-Za-z_][A-Za-z0-9_]*)'
    sql = re.sub(pattern_2, r',\n    \2."\3" AS "\1"', sql)

    return sql


def quote_schema_table_references(sql: str) -> str:
    return re.sub(
        r'"([^"]+)"\.([A-Za-z_][A-Za-z0-9_]*)',
        r'"\1"."\2"',
        sql,
    )


def quote_alias_column_references(sql: str) -> str:
    aliases = extract_table_aliases(sql)

    for alias in aliases:
        sql = re.sub(
            rf'\b{re.escape(alias)}\.([A-Za-z_][A-Za-z0-9_]*)\b',
            rf'{alias}."\1"',
            sql,
        )

    return sql


def extract_table_aliases(sql: str) -> set[str]:
    aliases = set()

    patterns = [
        r'\bFROM\s+"[^"]+"\."[^"]+"\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bJOIN\s+"[^"]+"\."[^"]+"\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bINNER\s+JOIN\s+"[^"]+"\."[^"]+"\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bLEFT\s+OUTER\s+JOIN\s+"[^"]+"\."[^"]+"\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bLEFT\s+JOIN\s+"[^"]+"\."[^"]+"\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bRIGHT\s+JOIN\s+"[^"]+"\."[^"]+"\s+([A-Za-z_][A-Za-z0-9_]*)',
        r'\bFULL\s+JOIN\s+"[^"]+"\."[^"]+"\s+([A-Za-z_][A-Za-z0-9_]*)',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, sql, flags=re.IGNORECASE):
            alias = match.group(1)
            if alias.upper() not in {"ON", "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "FULL"}:
                aliases.add(alias)

    return aliases


def convert_simple_string_concat(sql: str) -> str:
    return sql.replace(" + ' ' + ", " || ' ' || ")


def contains_sqlserver_xml_methods(sql: str) -> bool:
    return bool(
        re.search(
            r'(\.nodes\s*\(|\.value\s*\(|\."nodes"\s*\(|\."value"\s*\(|\bCROSS\s+APPLY\b|\bOUTER\s+APPLY\b)',
            sql,
            re.IGNORECASE,
        )
    )


def convert_simple_pivot_to_case(sql: str) -> str:
    pivot_pattern = re.compile(
        r"""
        CREATE\s+(?:OR\s+ALTER\s+)?VIEW\s+.*?\s+AS\s+
        SELECT\s+(?P<outer_select>.*?)\s+
        FROM\s*\(
            (?P<inner_query>.*?)
        \)\s+AS\s+(?P<inner_alias>\w+)\s+
        PIVOT\s*
        \(
            \s*SUM\("?(?P<measure>\w+)"?\)\s*
            FOR\s+"?(?P<pivot_col>\w+)"?\s*
            IN\s*\((?P<pivot_values>.*?)\)
        \)\s+AS\s+(?P<pivot_alias>\w+)
        """,
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    match = pivot_pattern.search(sql)

    if not match:
        raise ValueError("PIVOT detected but pattern is too complex.")

    inner_query = match.group("inner_query").strip()
    measure = match.group("measure")
    pivot_col = match.group("pivot_col")

    pivot_values = [
        value.strip().replace('"', "").replace("[", "").replace("]", "")
        for value in match.group("pivot_values").split(",")
    ]

    outer_items = [
        item.strip()
        for item in match.group("outer_select").split(",")
        if item.strip()
    ]

    non_pivot_columns = []

    for item in outer_items:
        clean_item = item.replace('"', "")
        clean_item = re.sub(r"^\w+\.", "", clean_item)

        if clean_item not in pivot_values:
            non_pivot_columns.append(item)

    case_columns = [
        f'SUM(CASE WHEN "{pivot_col}" = {value} THEN "{measure}" ELSE 0 END) AS "{value}"'
        for value in pivot_values
    ]

    final_select = ",\n    ".join(non_pivot_columns + case_columns)
    group_by = ",\n    ".join(non_pivot_columns)

    return f'''
SELECT
    {final_select}
FROM (
    {inner_query}
) AS source_data
GROUP BY
    {group_by}
'''