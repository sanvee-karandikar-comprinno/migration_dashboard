from pymongo import MongoClient
from pymongo.database import Database

from connectors.models import ServerConnectionConfig
from connectors.exceptions import DatabaseConnectionError


class MongoPoolFactory:
    @staticmethod
    def create_client_from_config(config: ServerConnectionConfig) -> MongoClient:
        if config.username and config.password:
            uri = (
                f"mongodb://{quote_plus_safe(config.username)}:"
                f"{quote_plus_safe(config.password)}@"
                f"{config.host}:{config.port}/"
                f"?authSource={config.auth_source or 'admin'}"
            )
        else:
            uri = f"mongodb://{config.host}:{config.port}/"

        return MongoClient(
            uri,
            maxPoolSize=config.pool_size,
            serverSelectionTimeoutMS=5000,
        )

    @staticmethod
    def get_database(client: MongoClient, database_name: str) -> Database:
        return client[database_name]

    @staticmethod
    def test_client(client: MongoClient) -> bool:
        try:
            client.admin.command("ping")
            return True
        except Exception as error:
            raise DatabaseConnectionError(str(error)) from error


def quote_plus_safe(value: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(value)