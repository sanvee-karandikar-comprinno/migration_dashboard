from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from connectors.models import ServerConnectionConfig, DatabaseConnectionConfig
from connectors.exceptions import UnsupportedDatabaseError, DatabaseConnectionError


class SQLPoolFactory:
    @staticmethod
    def create_server_engine(config: ServerConnectionConfig) -> Engine:
        db_type = config.db_type.lower()

        if db_type == "mssql":
            database = "master"
            url = SQLPoolFactory._mssql_url(config, database)
        elif db_type == "postgresql":
            database = "postgres"
            url = SQLPoolFactory._postgres_url(config, database)
        elif db_type == "mysql":
            url = SQLPoolFactory._mysql_url(config, database=None)
        else:
            raise UnsupportedDatabaseError(f"Unsupported SQL database type: {config.db_type}")

        return SQLPoolFactory._build_engine(url, config)

    @staticmethod
    def create_database_engine(config: DatabaseConnectionConfig) -> Engine:
        db_type = config.db_type.lower()

        if db_type == "mssql":
            url = SQLPoolFactory._mssql_url(config, config.database)
        elif db_type == "postgresql":
            url = SQLPoolFactory._postgres_url(config, config.database)
        elif db_type == "mysql":
            url = SQLPoolFactory._mysql_url(config, config.database)
        else:
            raise UnsupportedDatabaseError(f"Unsupported SQL database type: {config.db_type}")

        return SQLPoolFactory._build_engine(url, config)

    @staticmethod
    def _build_engine(url: str, config: ServerConnectionConfig) -> Engine:
        return create_engine(
            url,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout,
            pool_recycle=config.pool_recycle,
            pool_pre_ping=True,
            future=True,
        )

    @staticmethod
    def test_engine(engine: Engine) -> bool:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception as error:
            raise DatabaseConnectionError(str(error)) from error

    @staticmethod
    def list_databases(engine: Engine, db_type: str) -> list[str]:
        db_type = db_type.lower()

        if db_type == "mssql":
            query = """
            SELECT name
            FROM sys.databases
            WHERE database_id > 4
            ORDER BY name
            """

        elif db_type == "postgresql":
            query = """
            SELECT datname
            FROM pg_database
            WHERE datistemplate = false
            ORDER BY datname
            """

        elif db_type == "mysql":
            query = """
            SHOW DATABASES
            """

        else:
            raise UnsupportedDatabaseError(f"Unsupported SQL database type: {db_type}")

        with engine.connect() as connection:
            result = connection.execute(text(query))
            return [row[0] for row in result.fetchall()]

    @staticmethod
    def _mssql_url(config: ServerConnectionConfig, database: str) -> str:
        driver = config.driver or "ODBC Driver 17 for SQL Server"

        connection_string = (
            f"DRIVER={{{driver}}};"
            f"SERVER={config.host},{config.port};"
            f"DATABASE={database};"
            f"UID={config.username};"
            f"PWD={config.password};"
            f"TrustServerCertificate={'yes' if config.trust_server_certificate else 'no'};"
        )

        return f"mssql+pyodbc:///?odbc_connect={quote_plus(connection_string)}"

    @staticmethod
    def _postgres_url(config: ServerConnectionConfig, database: str) -> str:
        return (
            f"postgresql+psycopg2://{quote_plus(config.username or '')}:"
            f"{quote_plus(config.password or '')}@"
            f"{config.host}:{config.port}/{database}"
        )

    @staticmethod
    def _mysql_url(config: ServerConnectionConfig, database: str | None = None) -> str:
        base_url = (
            f"mysql+mysqlconnector://{quote_plus(config.username or '')}:"
            f"{quote_plus(config.password or '')}@"
            f"{config.host}:{config.port}"
        )

        if database:
            return f"{base_url}/{database}"

        return base_url