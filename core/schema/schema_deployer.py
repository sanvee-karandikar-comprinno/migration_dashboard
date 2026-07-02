"""
core/schema/schema_deployer.py
==============================
Deploys generated DDL statements to the target database.

Takes the output from schema_builder and executes it against the target.
Handles errors gracefully — reports failures without crashing the whole migration.
"""

import logging
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def deploy_schema(target_engine: Engine, schema_ddl: dict) -> dict:
    """
    Deploys all DDL statements to the target database.
    
    Args:
        target_engine: SQLAlchemy engine connected to the target database
        schema_ddl: Output from schema_builder.build_schema_ddl()
        
    Returns:
        Dictionary with deployment results:
        - schemas_created: count of schemas created
        - tables_created: count of tables successfully created
        - tables_failed: count of tables that failed
        - errors: list of {table_name, error, sql} for failures
    """
    result = {
        "schemas_created": 0,
        "tables_created": 0,
        "tables_failed": 0,
        "errors": [],
    }
    
    # If target is MongoDB, nothing to deploy
    if schema_ddl.get("message"):
        result["message"] = schema_ddl["message"]
        return result
    
    # Step 1: Create schemas (PostgreSQL only)
    for stmt in schema_ddl.get("schema_statements", []):
        try:
            with target_engine.connect() as conn:
                conn.execute(text(stmt))
                conn.commit()
            result["schemas_created"] += 1
        except Exception as e:
            logger.warning(f"Schema creation skipped: {e}")
    
    # Step 2: Create tables
    for table_info in schema_ddl.get("table_statements", []):
        table_name = table_info["table_name"]
        ddl = table_info["ddl"]
        
        try:
            with target_engine.connect() as conn:
                conn.execute(text(ddl))
                conn.commit()
            result["tables_created"] += 1
            logger.info(f"Created table: {table_name}")
        except Exception as e:
            result["tables_failed"] += 1
            result["errors"].append({
                "table_name": table_name,
                "error": str(e),
                "sql": ddl,
            })
            logger.error(f"Failed to create table {table_name}: {e}")
    
    return result


def create_target_database(target_engine: Engine, target_type: str, database_name: str) -> bool:
    """
    Creates the target database. If it already exists, DROPS and recreates it
    to ensure a clean migration without duplicate entry errors.
    
    Args:
        target_engine: Engine connected to the server (not a specific DB)
        target_type: 'mssql', 'mysql', or 'postgresql'
        database_name: Name of the database to create
        
    Returns:
        True if created/exists, False if failed
    """
    target = target_type.lower()
    
    try:
        if target == "mysql":
            with target_engine.connect() as conn:
                # Drop existing database for clean re-migration
                conn.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
                conn.execute(text(
                    f"CREATE DATABASE `{database_name}` "
                    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                ))
                conn.commit()
                
        elif target == "postgresql":
            # PostgreSQL requires autocommit for CREATE/DROP DATABASE
            with target_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                # Terminate active connections to the database before dropping
                conn.execute(text(
                    f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = :db_name AND pid <> pg_backend_pid()"
                ), {"db_name": database_name})
                conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
                conn.execute(text(f'CREATE DATABASE "{database_name}"'))
                    
        elif target == "mssql":
            with target_engine.connect() as conn:
                # Set to single user mode to kill connections, then drop
                exists = conn.execute(text(
                    f"SELECT 1 FROM sys.databases WHERE name = :db_name"
                ), {"db_name": database_name}).fetchone()
                
                if exists:
                    conn.execute(text(
                        f"ALTER DATABASE [{database_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE"
                    ))
                    conn.execute(text(f"DROP DATABASE [{database_name}]"))
                
                conn.execute(text(f"CREATE DATABASE [{database_name}]"))
                conn.commit()
        
        logger.info(f"Target database ready (fresh): {database_name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create database {database_name}: {e}")
        return False
