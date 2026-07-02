"""
core/auditor/dynamic_auditor.py
===============================
Generalized database schema auditor that works for MSSQL, MySQL, PostgreSQL, and MongoDB.

This auditor collects all metadata about a database:
- Tables / Collections
- Columns / Fields
- Primary keys
- Foreign keys
- Indexes
- Views
- Stored procedures, Functions, Triggers
- Row / Document counts

WHY ONE AUDITOR FOR ALL DATABASES?
- The migration dashboard needs to understand the source database structure
  before it can build the target schema.
- Using one generalized auditor (instead of separate ones per database)
  makes the code simpler and ensures consistent output format.
- The audit result is a standard Python dict that all downstream modules consume.
"""

import logging
from sqlalchemy import text
from sqlalchemy.engine import Engine
from pymongo import MongoClient

logger = logging.getLogger(__name__)


class DynamicAuditor:
    """
    Audits any supported database and returns a standardized metadata dictionary.
    
    Supported: mssql, mysql, postgresql, mongodb
    
    Usage:
        auditor = DynamicAuditor("mssql", engine, "AdventureWorks2025")
        report = auditor.run_audit()
    """

    def __init__(self, db_type: str, connection, database_name: str):
        """
        Args:
            db_type: One of 'mssql', 'mysql', 'postgresql', 'mongodb'
            connection: SQLAlchemy Engine (SQL) or MongoClient (MongoDB)
            database_name: Name of the specific database to audit
        """
        self.db_type = db_type.lower()
        self.connection = connection
        self.database_name = database_name

    def run_audit(self) -> dict:
        """
        Main entry point. Runs the full audit and returns a standardized report.
        
        Returns:
            Dictionary with keys: database_type, database_name, summary,
            tables, columns, primary_keys, foreign_keys, indexes,
            views, routines, triggers
        """
        if self.db_type in ("mssql", "mysql", "postgresql"):
            return self._audit_sql_database()
        elif self.db_type == "mongodb":
            return self._audit_mongodb_database()
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")

    # =========================================================================
    # SQL DATABASE AUDIT (works for MSSQL, MySQL, PostgreSQL)
    # =========================================================================

    def _audit_sql_database(self) -> dict:
        """Audits a SQL database using INFORMATION_SCHEMA (standard across SQL DBs)."""
        engine: Engine = self.connection

        tables = self._get_sql_tables(engine)
        columns = self._get_sql_columns(engine)
        primary_keys = self._get_sql_primary_keys(engine)
        foreign_keys = self._get_sql_foreign_keys(engine)
        indexes = self._get_sql_indexes(engine)
        views = self._get_sql_views(engine)
        routines = self._get_sql_routines(engine)
        triggers = self._get_sql_triggers(engine)

        return {
            "database_type": self.db_type,
            "database_name": self.database_name,
            "summary": {
                "total_tables": len(tables),
                "total_columns": len(columns),
                "total_primary_keys": len(primary_keys),
                "total_foreign_keys": len(foreign_keys),
                "total_indexes": len(indexes),
                "total_views": len(views),
                "total_routines": len(routines),
                "total_triggers": len(triggers),
            },
            "tables": tables,
            "columns": columns,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
            "views": views,
            "routines": routines,
            "triggers": triggers,
        }

    def _get_sql_tables(self, engine: Engine) -> list[dict]:
        """Gets all user tables with row counts."""
        if self.db_type == "mssql":
            query = text("""
                SELECT t.TABLE_SCHEMA, t.TABLE_NAME,
                       (SELECT SUM(p.rows) FROM sys.partitions p 
                        INNER JOIN sys.tables st ON p.object_id = st.object_id
                        INNER JOIN sys.schemas ss ON st.schema_id = ss.schema_id
                        WHERE ss.name = t.TABLE_SCHEMA AND st.name = t.TABLE_NAME
                        AND p.index_id IN (0, 1)) as row_count
                FROM INFORMATION_SCHEMA.TABLES t
                WHERE t.TABLE_TYPE = 'BASE TABLE'
                AND t.TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
                ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
            """)
        elif self.db_type == "mysql":
            query = text("""
                SELECT TABLE_SCHEMA as TABLE_SCHEMA, TABLE_NAME, TABLE_ROWS as row_count
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = :db_name AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)
        else:  # postgresql
            query = text("""
                SELECT table_schema as TABLE_SCHEMA, table_name as TABLE_NAME,
                       0 as row_count
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
            """)

        with engine.connect() as conn:
            if self.db_type == "mysql":
                result = conn.execute(query, {"db_name": self.database_name})
            else:
                result = conn.execute(query)
            
            tables = []
            for row in result:
                tables.append({
                    "schema_name": row[0] if row[0] else "public",
                    "table_name": row[1],
                    "row_count": int(row[2]) if row[2] else 0,
                })
            return tables

    def _get_sql_columns(self, engine: Engine) -> list[dict]:
        """Gets all columns with their data types and properties."""
        if self.db_type == "mssql":
            query = text("""
                SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION,
                       DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION,
                       NUMERIC_SCALE, IS_NULLABLE, COLUMN_DEFAULT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
                ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
            """)
        elif self.db_type == "mysql":
            query = text("""
                SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION,
                       DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION,
                       NUMERIC_SCALE, IS_NULLABLE, COLUMN_DEFAULT
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :db_name
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """)
        else:  # postgresql
            query = text("""
                SELECT table_schema, table_name, column_name, ordinal_position,
                       data_type, character_maximum_length, numeric_precision,
                       numeric_scale, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name, ordinal_position
            """)

        with engine.connect() as conn:
            if self.db_type == "mysql":
                result = conn.execute(query, {"db_name": self.database_name})
            else:
                result = conn.execute(query)
            
            columns = []
            for row in result:
                columns.append({
                    "schema_name": row[0],
                    "table_name": row[1],
                    "column_name": row[2],
                    "ordinal_position": row[3],
                    "data_type": row[4],
                    "character_maximum_length": row[5],
                    "numeric_precision": row[6],
                    "numeric_scale": row[7],
                    "is_nullable": row[8],
                    "column_default": str(row[9]) if row[9] else None,
                })
            return columns

    def _get_sql_primary_keys(self, engine: Engine) -> list[dict]:
        """Gets all primary key constraints."""
        if self.db_type == "mssql":
            query = text("""
                SELECT tc.TABLE_SCHEMA, tc.TABLE_NAME, kcu.COLUMN_NAME, tc.CONSTRAINT_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                    AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
                WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                AND tc.TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
                ORDER BY tc.TABLE_SCHEMA, tc.TABLE_NAME, kcu.ORDINAL_POSITION
            """)
        elif self.db_type == "mysql":
            query = text("""
                SELECT tc.TABLE_SCHEMA, tc.TABLE_NAME, kcu.COLUMN_NAME, tc.CONSTRAINT_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                    AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
                    AND tc.TABLE_NAME = kcu.TABLE_NAME
                WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                AND tc.TABLE_SCHEMA = :db_name
                ORDER BY tc.TABLE_NAME, kcu.ORDINAL_POSITION
            """)
        else:  # postgresql
            query = text("""
                SELECT tc.table_schema, tc.table_name, kcu.column_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
            """)

        with engine.connect() as conn:
            if self.db_type == "mysql":
                result = conn.execute(query, {"db_name": self.database_name})
            else:
                result = conn.execute(query)
            
            pks = []
            for row in result:
                pks.append({
                    "schema_name": row[0],
                    "table_name": row[1],
                    "column_name": row[2],
                    "constraint_name": row[3],
                })
            return pks

    def _get_sql_foreign_keys(self, engine: Engine) -> list[dict]:
        """Gets all foreign key constraints."""
        if self.db_type == "mssql":
            query = text("""
                SELECT
                    kcu.TABLE_SCHEMA, kcu.TABLE_NAME, kcu.COLUMN_NAME,
                    kcu.CONSTRAINT_NAME,
                    kcu2.TABLE_SCHEMA AS ref_schema,
                    kcu2.TABLE_NAME AS ref_table,
                    kcu2.COLUMN_NAME AS ref_column
                FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                    AND rc.CONSTRAINT_SCHEMA = kcu.TABLE_SCHEMA
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
                    ON rc.UNIQUE_CONSTRAINT_NAME = kcu2.CONSTRAINT_NAME
                    AND rc.UNIQUE_CONSTRAINT_SCHEMA = kcu2.TABLE_SCHEMA
                WHERE kcu.TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
                ORDER BY kcu.TABLE_SCHEMA, kcu.TABLE_NAME
            """)
        elif self.db_type == "mysql":
            query = text("""
                SELECT
                    kcu.TABLE_SCHEMA, kcu.TABLE_NAME, kcu.COLUMN_NAME,
                    kcu.CONSTRAINT_NAME,
                    kcu.REFERENCED_TABLE_SCHEMA AS ref_schema,
                    kcu.REFERENCED_TABLE_NAME AS ref_table,
                    kcu.REFERENCED_COLUMN_NAME AS ref_column
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                WHERE kcu.REFERENCED_TABLE_NAME IS NOT NULL
                AND kcu.TABLE_SCHEMA = :db_name
                ORDER BY kcu.TABLE_NAME
            """)
        else:  # postgresql
            query = text("""
                SELECT
                    tc.table_schema, tc.table_name, kcu.column_name,
                    tc.constraint_name,
                    ccu.table_schema AS ref_schema,
                    ccu.table_name AS ref_table,
                    ccu.column_name AS ref_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY tc.table_schema, tc.table_name
            """)

        with engine.connect() as conn:
            if self.db_type == "mysql":
                result = conn.execute(query, {"db_name": self.database_name})
            else:
                result = conn.execute(query)
            
            fks = []
            for row in result:
                fks.append({
                    "schema_name": row[0],
                    "table_name": row[1],
                    "column_name": row[2],
                    "constraint_name": row[3],
                    "ref_schema": row[4],
                    "ref_table": row[5],
                    "ref_column": row[6],
                })
            return fks

    def _get_sql_indexes(self, engine: Engine) -> list[dict]:
        """Gets all indexes (excluding primary keys)."""
        if self.db_type == "mssql":
            query = text("""
                SELECT s.name AS schema_name, t.name AS table_name,
                       i.name AS index_name, i.is_unique,
                       STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS columns
                FROM sys.indexes i
                JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                JOIN sys.tables t ON i.object_id = t.object_id
                JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE i.is_primary_key = 0 AND i.type > 0 AND i.name IS NOT NULL
                AND s.name NOT IN ('sys', 'INFORMATION_SCHEMA')
                GROUP BY s.name, t.name, i.name, i.is_unique
                ORDER BY s.name, t.name, i.name
            """)
        elif self.db_type == "mysql":
            query = text("""
                SELECT TABLE_SCHEMA, TABLE_NAME, INDEX_NAME,
                       CASE WHEN NON_UNIQUE = 0 THEN 1 ELSE 0 END AS is_unique,
                       GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns
                FROM INFORMATION_SCHEMA.STATISTICS
                WHERE TABLE_SCHEMA = :db_name AND INDEX_NAME != 'PRIMARY'
                GROUP BY TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, NON_UNIQUE
                ORDER BY TABLE_NAME, INDEX_NAME
            """)
        else:  # postgresql
            query = text("""
                SELECT schemaname, tablename, indexname,
                       CASE WHEN indexdef LIKE '%UNIQUE%' THEN 1 ELSE 0 END AS is_unique,
                       indexdef AS columns
                FROM pg_indexes
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                AND indexname NOT LIKE '%_pkey'
                ORDER BY schemaname, tablename, indexname
            """)

        with engine.connect() as conn:
            if self.db_type == "mysql":
                result = conn.execute(query, {"db_name": self.database_name})
            else:
                result = conn.execute(query)
            
            indexes = []
            for row in result:
                indexes.append({
                    "schema_name": row[0],
                    "table_name": row[1],
                    "index_name": row[2],
                    "is_unique": bool(row[3]),
                    "columns": row[4] if row[4] else "",
                })
            return indexes

    def _get_sql_views(self, engine: Engine) -> list[dict]:
        """Gets all views with their definitions."""
        if self.db_type == "mssql":
            query = text("""
                SELECT TABLE_SCHEMA, TABLE_NAME, VIEW_DEFINITION
                FROM INFORMATION_SCHEMA.VIEWS
                WHERE TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """)
        elif self.db_type == "mysql":
            query = text("""
                SELECT TABLE_SCHEMA, TABLE_NAME, VIEW_DEFINITION
                FROM INFORMATION_SCHEMA.VIEWS
                WHERE TABLE_SCHEMA = :db_name
                ORDER BY TABLE_NAME
            """)
        else:  # postgresql
            query = text("""
                SELECT schemaname, viewname, definition
                FROM pg_views
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY schemaname, viewname
            """)

        with engine.connect() as conn:
            if self.db_type == "mysql":
                result = conn.execute(query, {"db_name": self.database_name})
            else:
                result = conn.execute(query)
            
            views = []
            for row in result:
                views.append({
                    "schema_name": row[0],
                    "view_name": row[1],
                    "definition": row[2] if row[2] else "",
                })
            return views

    def _get_sql_routines(self, engine: Engine) -> list[dict]:
        """Gets stored procedures and functions."""
        if self.db_type == "mssql":
            query = text("""
                SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE, ROUTINE_DEFINITION
                FROM INFORMATION_SCHEMA.ROUTINES
                WHERE ROUTINE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
                ORDER BY ROUTINE_SCHEMA, ROUTINE_NAME
            """)
        elif self.db_type == "mysql":
            query = text("""
                SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE, ROUTINE_DEFINITION
                FROM INFORMATION_SCHEMA.ROUTINES
                WHERE ROUTINE_SCHEMA = :db_name
                ORDER BY ROUTINE_NAME
            """)
        else:  # postgresql
            query = text("""
                SELECT n.nspname AS schema, p.proname AS name,
                       CASE WHEN p.prokind = 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END AS type,
                       pg_get_functiondef(p.oid) AS definition
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY n.nspname, p.proname
            """)

        with engine.connect() as conn:
            if self.db_type == "mysql":
                result = conn.execute(query, {"db_name": self.database_name})
            else:
                result = conn.execute(query)
            
            routines = []
            for row in result:
                routines.append({
                    "schema_name": row[0],
                    "routine_name": row[1],
                    "routine_type": row[2],
                    "definition": row[3] if row[3] else "",
                })
            return routines

    def _get_sql_triggers(self, engine: Engine) -> list[dict]:
        """Gets all triggers."""
        if self.db_type == "mssql":
            query = text("""
                SELECT s.name AS schema_name, t.name AS table_name,
                       tr.name AS trigger_name, m.definition
                FROM sys.triggers tr
                JOIN sys.tables t ON tr.parent_id = t.object_id
                JOIN sys.schemas s ON t.schema_id = s.schema_id
                LEFT JOIN sys.sql_modules m ON tr.object_id = m.object_id
                WHERE s.name NOT IN ('sys', 'INFORMATION_SCHEMA')
                ORDER BY s.name, t.name, tr.name
            """)
        elif self.db_type == "mysql":
            query = text("""
                SELECT TRIGGER_SCHEMA, EVENT_OBJECT_TABLE,
                       TRIGGER_NAME, ACTION_STATEMENT
                FROM INFORMATION_SCHEMA.TRIGGERS
                WHERE TRIGGER_SCHEMA = :db_name
                ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME
            """)
        else:  # postgresql
            query = text("""
                SELECT trigger_schema, event_object_table,
                       trigger_name, action_statement
                FROM information_schema.triggers
                WHERE trigger_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY trigger_schema, event_object_table, trigger_name
            """)

        with engine.connect() as conn:
            if self.db_type == "mysql":
                result = conn.execute(query, {"db_name": self.database_name})
            else:
                result = conn.execute(query)
            
            triggers = []
            for row in result:
                triggers.append({
                    "schema_name": row[0],
                    "table_name": row[1],
                    "trigger_name": row[2],
                    "definition": row[3] if row[3] else "",
                })
            return triggers

    # =========================================================================
    # MONGODB AUDIT
    # =========================================================================

    def _audit_mongodb_database(self) -> dict:
        """
        Audits a MongoDB database.
        
        MongoDB doesn't have schemas, views, or stored procedures in the SQL sense.
        We collect: collections, sample fields, indexes, and document counts.
        """
        client: MongoClient = self.connection
        db = client[self.database_name]

        collections = []
        all_fields = []
        all_indexes = []

        for coll_name in sorted(db.list_collection_names()):
            collection = db[coll_name]
            doc_count = collection.estimated_document_count()
            
            collections.append({
                "schema_name": self.database_name,
                "table_name": coll_name,
                "row_count": doc_count,
            })

            # Sample documents to infer fields (like columns in SQL)
            sample = collection.find_one()
            if sample:
                for field_name, value in sample.items():
                    all_fields.append({
                        "schema_name": self.database_name,
                        "table_name": coll_name,
                        "column_name": field_name,
                        "ordinal_position": 0,
                        "data_type": type(value).__name__,
                        "character_maximum_length": None,
                        "numeric_precision": None,
                        "numeric_scale": None,
                        "is_nullable": "YES",
                        "column_default": None,
                    })

            # Get indexes for this collection
            for idx_name, idx_info in collection.index_information().items():
                if idx_name == "_id_":
                    continue  # Skip default _id index
                all_indexes.append({
                    "schema_name": self.database_name,
                    "table_name": coll_name,
                    "index_name": idx_name,
                    "is_unique": idx_info.get("unique", False),
                    "columns": ", ".join([f"{k}" for k, _ in idx_info["key"]]),
                })

        return {
            "database_type": self.db_type,
            "database_name": self.database_name,
            "summary": {
                "total_tables": len(collections),
                "total_columns": len(all_fields),
                "total_primary_keys": len(collections),  # Every collection has _id
                "total_foreign_keys": 0,  # MongoDB doesn't enforce FK
                "total_indexes": len(all_indexes),
                "total_views": 0,
                "total_routines": 0,
                "total_triggers": 0,
            },
            "tables": collections,
            "columns": all_fields,
            "primary_keys": [{"schema_name": c["schema_name"], "table_name": c["table_name"],
                              "column_name": "_id", "constraint_name": "_id_"} for c in collections],
            "foreign_keys": [],
            "indexes": all_indexes,
            "views": [],
            "routines": [],
            "triggers": [],
        }
