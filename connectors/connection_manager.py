"""
connectors/connection_manager.py
================================
Centralized connection management with proper connection pooling.

This module manages ALL database connections for the migration dashboard.
It uses SQLAlchemy's built-in connection pooling for SQL databases and
PyMongo's built-in client pooling for MongoDB.

WHY CONNECTION POOLING?
- Opening a new database connection is expensive (TCP handshake, auth, etc.)
- A pool keeps connections open and reuses them for multiple operations.
- This makes the dashboard much faster and more reliable.
- Without pooling, the dashboard would be slow and could exhaust server connections.

KEY POOLING PARAMETERS EXPLAINED:
- pool_size: Keeps this many connections always ready in the pool.
- max_overflow: Allows this many EXTRA connections during busy periods.
- pool_timeout: If all connections are busy, wait this many seconds before failing.
- pool_recycle: Close and reopen connections after this many seconds to prevent stale connections.
- pool_pre_ping: Sends a test query before using a connection to make sure it's still alive.
  This prevents "connection reset" errors in long-running dashboards.

MONGODB NOTE:
MongoClient already manages its own connection pool internally.
We just configure maxPoolSize when creating the client.
"""

import os
import logging
from typing import Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from connectors.models import ServerConnectionConfig, PoolConfig

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages all database connections with pooling.
    
    Maintains dictionaries of:
    - server_engines: SQLAlchemy engines connected to server (for listing databases)
    - database_engines: SQLAlchemy engines connected to specific databases
    - mongo_clients: PyMongo clients (MongoDB)
    
    Usage:
        manager = ConnectionManager(pool_config)
        engine = manager.connect_server("source", config)
        databases = manager.list_databases("source", config)
        db_engine = manager.connect_database("source_db", config, "AdventureWorks")
        manager.close_all()
    """

    def __init__(self, pool_config: Optional[PoolConfig] = None):
        """
        Initialize the connection manager.
        
        Args:
            pool_config: Pool settings (uses defaults if not provided)
        """
        # Use provided config or load defaults from environment variables
        self.pool_config = pool_config or self._load_pool_config_from_env()
        
        # Dictionaries storing active connections (reused instead of recreating)
        self.server_engines: dict[str, Engine] = {}
        self.database_engines: dict[str, Engine] = {}
        self.mongo_clients: dict[str, MongoClient] = {}

    def _load_pool_config_from_env(self) -> PoolConfig:
        """
        Loads pool configuration from environment variables.
        Falls back to sensible defaults if env vars are not set.
        """
        return PoolConfig(
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
            pool_pre_ping=os.getenv("DB_POOL_PRE_PING", "true").lower() == "true",
            mongo_max_pool_size=int(os.getenv("MONGODB_MAX_POOL_SIZE", "20")),
            mongo_server_selection_timeout_ms=int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "5000")),
        )

    # =========================================================================
    # CONNECTION CREATION
    # =========================================================================

    def connect_server(self, name: str, config: ServerConnectionConfig) -> object:
        """
        Connect to a database server (not a specific database).
        Used for listing available databases.
        
        Args:
            name: A label for this connection (e.g., "source" or "target")
            config: Server connection parameters
            
        Returns:
            SQLAlchemy Engine or MongoClient depending on db_type
            
        Raises:
            ConnectionError: If connection fails
        """
        db_type = config.db_type.lower()

        if db_type in ("mssql", "mysql", "postgresql"):
            engine = self._create_sql_engine(config, database=None)
            self._test_sql_engine(engine)
            self.server_engines[name] = engine
            return engine

        if db_type == "mongodb":
            client = self._create_mongo_client(config)
            self._test_mongo_client(client)
            self.mongo_clients[name] = client
            return client

        raise ValueError(f"Unsupported database type: {db_type}")

    def connect_database(self, name: str, config: ServerConnectionConfig, database: str) -> object:
        """
        Connect to a specific database on a server.
        Used for performing actual migration operations.
        
        Args:
            name: A label for this connection (e.g., "source_db" or "target_db")
            config: Server connection parameters
            database: Name of the specific database to connect to
            
        Returns:
            SQLAlchemy Engine or MongoClient
        """
        db_type = config.db_type.lower()

        if db_type in ("mssql", "mysql", "postgresql"):
            engine = self._create_sql_engine(config, database=database)
            self._test_sql_engine(engine)
            self.database_engines[name] = engine
            return engine

        if db_type == "mongodb":
            client = self._create_mongo_client(config)
            self._test_mongo_client(client)
            self.mongo_clients[name] = client
            return client

        raise ValueError(f"Unsupported database type: {db_type}")

    # =========================================================================
    # DATABASE LISTING
    # =========================================================================

    def list_databases(self, name: str, config: ServerConnectionConfig) -> list[str]:
        """
        List all available databases on a connected server.
        Filters out system databases automatically.
        
        Args:
            name: Connection label (must have been connected via connect_server first)
            config: Server connection config (needed to know db_type)
            
        Returns:
            List of database names available on the server
        """
        db_type = config.db_type.lower()

        if db_type == "mssql":
            engine = self.server_engines.get(name)
            if not engine:
                engine = self.connect_server(name, config)
            with engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT name FROM sys.databases "
                    "WHERE name NOT IN ('master', 'tempdb', 'model', 'msdb') "
                    "ORDER BY name"
                ))
                return [row[0] for row in result]

        elif db_type == "mysql":
            engine = self.server_engines.get(name)
            if not engine:
                engine = self.connect_server(name, config)
            with engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
                    "WHERE SCHEMA_NAME NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys') "
                    "ORDER BY SCHEMA_NAME"
                ))
                return [row[0] for row in result]

        elif db_type == "postgresql":
            engine = self.server_engines.get(name)
            if not engine:
                engine = self.connect_server(name, config)
            with engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT datname FROM pg_database "
                    "WHERE datistemplate = false AND datname NOT IN ('postgres') "
                    "ORDER BY datname"
                ))
                return [row[0] for row in result]

        elif db_type == "mongodb":
            client = self.mongo_clients.get(name)
            if not client:
                client = self.connect_server(name, config)
            # Filter out MongoDB system databases
            all_dbs = client.list_database_names()
            system_dbs = {"admin", "local", "config"}
            return [db for db in sorted(all_dbs) if db not in system_dbs]

        return []

    # =========================================================================
    # CONNECTION CLEANUP
    # =========================================================================

    def close_all(self):
        """
        Safely close ALL open connections and release pool resources.
        Call this when the dashboard is shutting down or resetting.
        """
        # Close all SQLAlchemy engines (this also closes all pooled connections)
        for name, engine in self.server_engines.items():
            try:
                engine.dispose()
                logger.info(f"Closed server engine: {name}")
            except Exception as e:
                logger.warning(f"Error closing server engine {name}: {e}")
        self.server_engines.clear()

        for name, engine in self.database_engines.items():
            try:
                engine.dispose()
                logger.info(f"Closed database engine: {name}")
            except Exception as e:
                logger.warning(f"Error closing database engine {name}: {e}")
        self.database_engines.clear()

        # Close all MongoDB clients
        for name, client in self.mongo_clients.items():
            try:
                client.close()
                logger.info(f"Closed MongoDB client: {name}")
            except Exception as e:
                logger.warning(f"Error closing MongoDB client {name}: {e}")
        self.mongo_clients.clear()

    # =========================================================================
    # INTERNAL: SQL ENGINE CREATION WITH POOLING
    # =========================================================================

    def _create_sql_engine(self, config: ServerConnectionConfig, database: Optional[str] = None) -> Engine:
        """
        Creates a SQLAlchemy engine with connection pooling.
        
        The engine maintains a pool of database connections that are reused.
        This is much faster than opening/closing connections for every query.
        
        Args:
            config: Server connection parameters
            database: Specific database name (None = server-level connection)
            
        Returns:
            SQLAlchemy Engine with pooling configured
        """
        url = self._build_sql_url(config, database)
        
        # Create engine with connection pooling parameters
        # These settings come from .env or PoolConfig defaults
        engine = create_engine(
            url,
            # pool_size: How many connections to keep permanently open
            pool_size=self.pool_config.pool_size,
            # max_overflow: How many extra connections during peak load
            max_overflow=self.pool_config.max_overflow,
            # pool_timeout: Seconds to wait for a connection before error
            pool_timeout=self.pool_config.pool_timeout,
            # pool_recycle: Recreate connections after this many seconds
            # Prevents "server has gone away" errors in long-running dashboards
            pool_recycle=self.pool_config.pool_recycle,
            # pool_pre_ping: Test connection is alive before using it
            # Prevents errors from stale/broken connections
            pool_pre_ping=self.pool_config.pool_pre_ping,
        )
        return engine

    def _build_sql_url(self, config: ServerConnectionConfig, database: Optional[str] = None) -> str:
        """
        Builds a SQLAlchemy connection URL for the given database type.
        
        URL format varies by database:
        - MSSQL: mssql+pyodbc:///?odbc_connect=<full_odbc_string>
        - MySQL: mysql+mysqlconnector://user:pass@host:port/db
        - PostgreSQL: postgresql+psycopg2://user:pass@host:port/db
        """
        db_type = config.db_type.lower()
        
        # URL-encode username and password to handle special characters
        user = quote_plus(config.username) if config.username else ""
        password = quote_plus(config.password) if config.password else ""

        if db_type == "mssql":
            # MSSQL uses pyodbc as the DBAPI driver.
            # We build a raw ODBC connection string and pass it via odbc_connect parameter.
            # This is more reliable than URL-based connection for MSSQL.
            driver = config.driver
            host = config.host
            db_name = database or "master"
            
            # Determine server string:
            # If host contains a backslash (named instance like localhost\SQLEXPRESS),
            # use the instance name directly without port.
            # Otherwise use host,port format.
            if "\\" in host:
                server_str = host  # Named instance — port not needed
            else:
                server_str = f"{host},{config.port}"
            
            if config.trusted_connection:
                # Windows Authentication — no username/password needed
                odbc_str = (
                    f"DRIVER={{{driver}}};"
                    f"SERVER={server_str};"
                    f"DATABASE={db_name};"
                    f"Trusted_Connection=yes;"
                    f"TrustServerCertificate=yes;"
                )
            else:
                # SQL Server Authentication
                odbc_str = (
                    f"DRIVER={{{driver}}};"
                    f"SERVER={server_str};"
                    f"DATABASE={db_name};"
                    f"UID={config.username};"
                    f"PWD={config.password};"
                    f"TrustServerCertificate=yes;"
                )
            
            return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_str)}"

        elif db_type == "mysql":
            db_part = f"/{database}" if database else ""
            return f"mysql+mysqlconnector://{user}:{password}@{config.host}:{config.port}{db_part}?charset=utf8mb4"

        elif db_type == "postgresql":
            db_part = f"/{database}" if database else "/postgres"
            return f"postgresql+psycopg2://{user}:{password}@{config.host}:{config.port}{db_part}"

        raise ValueError(f"Cannot build URL for database type: {db_type}")

    # =========================================================================
    # INTERNAL: MONGODB CLIENT CREATION WITH POOLING
    # =========================================================================

    def _create_mongo_client(self, config: ServerConnectionConfig) -> MongoClient:
        """
        Creates a MongoDB client with connection pooling.
        
        MongoClient internally manages its own connection pool.
        We configure maxPoolSize to control how many connections it maintains.
        The client reuses connections automatically — no manual pool management needed.
        
        Args:
            config: Server connection parameters
            
        Returns:
            MongoClient with pooling configured
        """
        # Check if a full URI is provided (overrides individual settings)
        uri = os.getenv("MONGODB_URI", "")
        
        if uri:
            # Use the provided full connection string
            client = MongoClient(
                uri,
                maxPoolSize=self.pool_config.mongo_max_pool_size,
                serverSelectionTimeoutMS=self.pool_config.mongo_server_selection_timeout_ms,
            )
        elif config.username and config.password:
            # Build authenticated connection
            client = MongoClient(
                host=config.host,
                port=config.port,
                username=config.username,
                password=config.password,
                maxPoolSize=self.pool_config.mongo_max_pool_size,
                serverSelectionTimeoutMS=self.pool_config.mongo_server_selection_timeout_ms,
            )
        else:
            # Connect without authentication (local development)
            client = MongoClient(
                host=config.host,
                port=config.port,
                maxPoolSize=self.pool_config.mongo_max_pool_size,
                serverSelectionTimeoutMS=self.pool_config.mongo_server_selection_timeout_ms,
            )
        
        return client

    # =========================================================================
    # INTERNAL: CONNECTION TESTING
    # =========================================================================

    def _test_sql_engine(self, engine: Engine):
        """Tests that a SQL engine can actually connect to the server."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            engine.dispose()
            raise ConnectionError(f"Failed to connect to SQL database: {e}")

    def _test_mongo_client(self, client: MongoClient):
        """Tests that a MongoDB client can actually reach the server."""
        try:
            # ping command verifies the server is reachable
            client.admin.command("ping")
        except ConnectionFailure as e:
            client.close()
            raise ConnectionError(f"Failed to connect to MongoDB: {e}")
