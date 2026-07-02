"""
Unit tests for core migration components.
Run with: python -m pytest tests/ -v
"""
import pytest

from core.schema.type_mapper import map_data_type
from core.schema.schema_builder import (
    sanitize_identifier,
    format_table_name,
    format_identifier,
    build_create_table_statement,
)
from core.utils.retry import retry


# ─────────────────────────────────────────────────────────────────────────────
# type_mapper tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTypeMapper:

    def test_mssql_int_to_postgresql(self):
        assert map_data_type("int", "postgresql", {}) == "INTEGER"

    def test_mssql_nvarchar_max_to_postgresql(self):
        col = {"character_maximum_length": -1}
        assert map_data_type("nvarchar", "postgresql", col) == "TEXT"

    def test_mssql_nvarchar_length_to_postgresql(self):
        col = {"character_maximum_length": 100}
        assert map_data_type("nvarchar", "postgresql", col) == "VARCHAR(100)"

    def test_mssql_uniqueidentifier_to_postgresql(self):
        assert map_data_type("uniqueidentifier", "postgresql", {}) == "UUID"

    def test_mssql_uniqueidentifier_to_mysql(self):
        assert map_data_type("uniqueidentifier", "mysql", {}) == "CHAR(36)"

    def test_postgresql_boolean_to_mysql(self):
        assert map_data_type("boolean", "mysql", {}) == "TINYINT(1)"

    def test_postgresql_uuid_to_mssql(self):
        assert map_data_type("uuid", "mssql", {}) == "UNIQUEIDENTIFIER"

    def test_mysql_tinytext_to_postgresql(self):
        assert map_data_type("tinytext", "postgresql", {}) == "TEXT"

    def test_mysql_json_to_postgresql(self):
        assert map_data_type("json", "postgresql", {}) == "JSON"

    def test_mysql_json_to_mssql(self):
        assert map_data_type("json", "mssql", {}) == "NVARCHAR(MAX)"

    def test_decimal_with_precision(self):
        col = {"numeric_precision": 10, "numeric_scale": 2}
        assert map_data_type("decimal", "postgresql", col) == "NUMERIC(10,2)"

    def test_postgresql_alias_int4(self):
        # int4 is a PostgreSQL internal alias for integer
        assert map_data_type("int4", "mysql", {}) == "INT"

    def test_postgresql_alias_bool(self):
        assert map_data_type("bool", "mssql", {}) == "BIT"

    def test_unknown_type_fallback(self):
        assert map_data_type("some_unknown_type", "postgresql", {}) == "TEXT"
        assert map_data_type("some_unknown_type", "mssql", {}) == "NVARCHAR(MAX)"


# ─────────────────────────────────────────────────────────────────────────────
# schema_builder tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaBuilder:

    def test_sanitize_identifier_spaces(self):
        assert sanitize_identifier("first name") == "first_name"

    def test_sanitize_identifier_dashes(self):
        assert sanitize_identifier("order-id") == "order_id"

    def test_format_table_mysql(self):
        result = format_table_name("dbo", "Orders", "mysql")
        assert result == "`dbo_orders`"

    def test_format_table_postgresql(self):
        result = format_table_name("dbo", "Orders", "postgresql")
        assert result == '"dbo"."Orders"'

    def test_format_table_mssql(self):
        result = format_table_name("dbo", "Orders", "mssql")
        assert result == "[dbo].[Orders]"

    def test_format_identifier_mysql(self):
        assert format_identifier("first_name", "mysql") == "`first_name`"

    def test_format_identifier_postgresql(self):
        assert format_identifier("first_name", "postgresql") == '"first_name"'

    def test_build_create_table_postgresql(self):
        columns = [
            {"column_name": "id", "data_type": "int", "is_nullable": "NO",
             "column_default": None, "character_maximum_length": None,
             "numeric_precision": None, "numeric_scale": None},
            {"column_name": "name", "data_type": "varchar", "is_nullable": "YES",
             "column_default": None, "character_maximum_length": 100,
             "numeric_precision": None, "numeric_scale": None},
        ]
        sql = build_create_table_statement("dbo", "Users", columns, "mssql", "postgresql")
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert '"id"' in sql
        assert '"name"' in sql
        assert "NOT NULL" in sql

    def test_build_create_table_mysql(self):
        columns = [
            {"column_name": "id", "data_type": "int", "is_nullable": "NO",
             "column_default": None, "character_maximum_length": None,
             "numeric_precision": None, "numeric_scale": None},
        ]
        sql = build_create_table_statement("dbo", "Users", columns, "mssql", "mysql")
        assert "`dbo_users`" in sql


# ─────────────────────────────────────────────────────────────────────────────
# retry tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRetry:

    def test_succeeds_on_first_try(self):
        call_count = {"n": 0}

        @retry(max_attempts=3, base_delay=0)
        def fn():
            call_count["n"] += 1
            return "ok"

        assert fn() == "ok"
        assert call_count["n"] == 1

    def test_retries_on_failure(self):
        call_count = {"n": 0}

        @retry(max_attempts=3, base_delay=0)
        def fn():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ValueError("transient")
            return "ok"

        assert fn() == "ok"
        assert call_count["n"] == 3

    def test_raises_after_max_attempts(self):
        @retry(max_attempts=2, base_delay=0)
        def fn():
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError):
            fn()

    def test_only_catches_specified_exceptions(self):
        @retry(max_attempts=3, base_delay=0, exceptions=(ValueError,))
        def fn():
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            fn()
