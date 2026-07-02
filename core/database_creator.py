from sqlalchemy import text
from sqlalchemy.engine import Engine
from pymongo import MongoClient


def normalize_database_name(name: str, db_type: str) -> str:
    if db_type in ["mysql", "postgresql"]:
        return name.lower()

    return name


def create_target_database(
    db_type: str,
    server_connection,
    target_database_name: str,
) -> str:
    db_type = db_type.lower()
    target_database_name = normalize_database_name(target_database_name, db_type)

    if db_type == "mssql":
        _create_mssql_database(server_connection, target_database_name)

    elif db_type == "mysql":
        _create_mysql_database(server_connection, target_database_name)

    elif db_type == "postgresql":
        _create_postgresql_database(server_connection, target_database_name)

    elif db_type == "mongodb":
        _create_mongodb_database(server_connection, target_database_name)

    else:
        raise ValueError(f"Unsupported target database type: {db_type}")

    return target_database_name


def _create_mssql_database(engine: Engine, database_name: str):
    query = f"""
    IF DB_ID('{database_name}') IS NULL
    BEGIN
        CREATE DATABASE [{database_name}]
    END
    """

    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(query))


def _create_mysql_database(engine: Engine, database_name: str):
    query = f"CREATE DATABASE IF NOT EXISTS `{database_name}`"

    with engine.connect() as conn:
        conn.execute(text(query))


def _create_postgresql_database(engine: Engine, database_name: str):
    check_query = """
    SELECT 1
    FROM pg_database
    WHERE datname = :database_name
    """

    create_query = f'CREATE DATABASE "{database_name}"'

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        exists = conn.execute(
            text(check_query),
            {"database_name": database_name},
        ).fetchone()

        if not exists:
            conn.execute(text(create_query))


def _create_mongodb_database(client: MongoClient, database_name: str):
    db = client[database_name]
    db["_migration_metadata"].insert_one({
        "message": "Database initialized for migration"
    })