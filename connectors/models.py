"""
connectors/models.py
====================
Data models for database connection configuration.

These dataclasses hold all connection parameters needed to connect to
any supported database (MSSQL, MySQL, PostgreSQL, MongoDB).
They are used by the ConnectionManager to create pooled connections.

Why dataclasses?
- Clean, typed structure for connection parameters
- Easy to create from .env values or Streamlit sidebar inputs
- No business logic — just data containers
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ServerConnectionConfig:
    """
    Configuration for connecting to a database SERVER (not a specific database).
    Used to list available databases on that server.
    
    Parameters:
        db_type: One of 'mssql', 'mysql', 'postgresql', 'mongodb'
        host: Server hostname or IP address
        port: Server port number
        username: Authentication username (optional for Windows Auth)
        password: Authentication password (optional for Windows Auth)
        driver: ODBC driver name (MSSQL only)
        trusted_connection: Use Windows Auth instead of username/password (MSSQL only)
    """
    db_type: str
    host: str = "localhost"
    port: int = 3306
    username: str = ""
    password: str = ""
    driver: str = "ODBC Driver 17 for SQL Server"
    trusted_connection: bool = False


@dataclass
class PoolConfig:
    """
    Connection pool settings. These control how connections are reused.
    
    Parameters:
        pool_size: Number of permanent connections in the pool (default: 5)
        max_overflow: Extra connections allowed above pool_size during peak load (default: 10)
        pool_timeout: Seconds to wait for a free connection before raising error (default: 30)
        pool_recycle: Seconds after which connections are recycled to prevent staleness (default: 3600)
        pool_pre_ping: Test connection health before using it (default: True)
        mongo_max_pool_size: Maximum connections for MongoDB client (default: 20)
        mongo_server_selection_timeout_ms: MongoDB server selection timeout (default: 5000)
    """
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    pool_pre_ping: bool = True
    mongo_max_pool_size: int = 20
    mongo_server_selection_timeout_ms: int = 5000
