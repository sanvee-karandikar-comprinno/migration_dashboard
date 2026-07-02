class ConnectionManagerError(Exception):
    pass


class UnsupportedDatabaseError(ConnectionManagerError):
    pass


class DatabaseConnectionError(ConnectionManagerError):
    pass