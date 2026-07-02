from connectors.connection_manager import ConnectionManager
from connectors.models import ServerConnectionConfig, DatabaseConnectionConfig
from core.auditor.dynamic_auditor import DynamicAuditor
from core.auditor.report_writer import save_audit_report
from core.database_creator import create_target_database
from core.schema.schema_builder import (
    build_create_schema_statements,
    build_create_schema_namespace_statements,
)
from core.schema.schema_deployer import deploy_schema
from core.data.data_migrator import migrate_data
from core.nosql.sql_to_mongo_migrator import migrate_sql_to_mongodb
from core.nosql.mongo_to_sql_migrator import migrate_mongodb_to_sql
from core.objects.object_migrator import migrate_programmable_objects
from dotenv import load_dotenv
import os


load_dotenv()


SUPPORTED_DATABASES = {
    "1": "mssql",
    "2": "mysql",
    "3": "postgresql",
    "4": "mongodb",
}


def ask_database_type(label: str) -> str:
    print(f"\nSelect {label} database type:")
    print("1. MSSQL")
    print("2. MySQL")
    print("3. PostgreSQL")
    print("4. MongoDB")

    choice = input("Enter choice number: ").strip()

    if choice not in SUPPORTED_DATABASES:
        raise ValueError("Invalid database type selected.")

    return SUPPORTED_DATABASES[choice]


def get_server_config_from_env(db_type: str) -> ServerConnectionConfig:
    db_type = db_type.lower()

    if db_type == "mssql":
        return ServerConnectionConfig(
            db_type="mssql",
            host=os.getenv("MSSQL_HOST"),
            port=int(os.getenv("MSSQL_PORT", "1433")),
            username=os.getenv("MSSQL_USERNAME"),
            password=os.getenv("MSSQL_PASSWORD"),
            driver=os.getenv("MSSQL_DRIVER", "ODBC Driver 17 for SQL Server"),
            trust_server_certificate=True,
        )

    if db_type == "mysql":
        return ServerConnectionConfig(
            db_type="mysql",
            host=os.getenv("MYSQL_HOST"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            username=os.getenv("MYSQL_USERNAME"),
            password=os.getenv("MYSQL_PASSWORD"),
        )

    if db_type == "postgresql":
        return ServerConnectionConfig(
            db_type="postgresql",
            host=os.getenv("POSTGRES_HOST"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            username=os.getenv("POSTGRES_USERNAME"),
            password=os.getenv("POSTGRES_PASSWORD"),
        )

    if db_type == "mongodb":
        return ServerConnectionConfig(
            db_type="mongodb",
            host=os.getenv("MONGODB_HOST"),
            port=int(os.getenv("MONGODB_PORT", "27017")),
            username=os.getenv("MONGODB_USERNAME") or None,
            password=os.getenv("MONGODB_PASSWORD") or None,
            auth_source=os.getenv("MONGODB_AUTH_SOURCE", "admin"),
        )

    raise ValueError(f"Unsupported database type: {db_type}")


def choose_database(manager: ConnectionManager, connection_name: str, db_type: str) -> str:
    databases = manager.list_databases(connection_name, db_type)

    if not databases:
        raise RuntimeError("No databases found.")

    print("\nAvailable databases:")
    for index, database in enumerate(databases, start=1):
        print(f"{index}. {database}")

    selected_index = int(input("\nSelect database number: "))

    if selected_index < 1 or selected_index > len(databases):
        raise ValueError("Invalid database selection.")

    return databases[selected_index - 1]


def build_database_config(
    server_config: ServerConnectionConfig,
    selected_database: str,
) -> DatabaseConnectionConfig:
    return DatabaseConnectionConfig(
        db_type=server_config.db_type,
        host=server_config.host,
        port=server_config.port,
        username=server_config.username,
        password=server_config.password,
        driver=server_config.driver,
        trust_server_certificate=server_config.trust_server_certificate,
        auth_source=server_config.auth_source,
        database=selected_database,
    )


def ask_migration_type() -> dict:
    print("\n========== MIGRATION TYPE ==========")
    print("1. Schema only")
    print("2. Schema + data")
    print("3. Schema + data + programmable objects")
    print("4. Full migration")

    choice = input("Enter migration type number: ").strip()

    migration_types = {
        "1": {
            "name": "schema_only",
            "schema": True,
            "data": False,
            "programmable_objects": False,
            "triggers": False,
            "cursors": False,
        },
        "2": {
            "name": "schema_and_data",
            "schema": True,
            "data": True,
            "programmable_objects": False,
            "triggers": False,
            "cursors": False,
        },
        "3": {
            "name": "schema_data_programmable_objects",
            "schema": True,
            "data": True,
            "programmable_objects": True,
            "triggers": False,
            "cursors": False,
        },
        "4": {
            "name": "full_migration",
            "schema": True,
            "data": True,
            "programmable_objects": True,
            "triggers": True,
            "cursors": True,
        },
    }

    if choice not in migration_types:
        raise ValueError("Invalid migration type selected.")

    selected = migration_types[choice]

    print(f"Selected migration type: {selected['name']}")

    return selected


def main():
    manager = ConnectionManager()

    print("\n========== SOURCE DATABASE ==========")
    source_type = ask_database_type("source")
    source_server_config = get_server_config_from_env(source_type)

    manager.connect_server("source_server", source_server_config)
    print(f"{source_type} source server connected successfully.")

    source_database_name = choose_database(
        manager,
        "source_server",
        source_type,
    )

    source_database_config = build_database_config(
        source_server_config,
        source_database_name,
    )

    manager.connect_database("source_database", source_database_config)
    print(f"Selected source database: {source_database_name}")

    source_connection = (
        manager.mongo_clients["source_database"]
        if source_type == "mongodb"
        else manager.database_engines["source_database"]
    )

    auditor = DynamicAuditor(
        db_type=source_type,
        connection=source_connection,
        database_name=source_database_name,
    )

    audit_report = auditor.run_audit()
    audit_path = save_audit_report(audit_report)

    print("\n========== SOURCE AUDIT SUMMARY ==========")
    for key, value in audit_report["summary"].items():
        print(f"{key}: {value}")

    print(f"\nAudit report saved at: {audit_path}")

    migration_type = ask_migration_type()

    proceed = input("\nProceed with migration? (y/n): ").strip().lower()

    if proceed != "y":
        print("Migration cancelled by user.")
        manager.close_all()
        return

    print("\n========== TARGET DATABASE ==========")

    target_type = ask_database_type("target")
    target_server_config = get_server_config_from_env(target_type)

    manager.connect_server("target_server", target_server_config)
    print(f"{target_type} target server connected successfully.")

    target_database_name = f"{source_database_name}_migration_target"

    target_server_connection = (
        manager.mongo_clients["target_server"]
        if target_type == "mongodb"
        else manager.server_engines["target_server"]
    )

    target_database_name = create_target_database(
        db_type=target_type,
        server_connection=target_server_connection,
        target_database_name=target_database_name,
    )

    print(f"Target database created/verified: {target_database_name}")

    target_database_config = build_database_config(
        target_server_config,
        target_database_name,
    )

    manager.connect_database(
        "target_database",
        target_database_config,
    )

    print(f"Connected to target database: {target_database_name}")

    # ── SQL → MongoDB ────────────────────────────────────────────────────────
    if source_type in ["mssql", "mysql", "postgresql"] and target_type == "mongodb":
        print("\n========== SQL TO MONGODB MIGRATION ==========")

        sql_source_connection = manager.database_engines["source_database"]
        mongo_target_connection = manager.mongo_clients["target_database"]

        sql_mongo_result = migrate_sql_to_mongodb(
            source_type=source_type,
            source_engine=sql_source_connection,
            mongo_client=mongo_target_connection,
            target_database_name=target_database_name,
            audit_report=audit_report,
            batch_size=1000,
        )

        print("\n========== SQL TO MONGODB MIGRATION SUMMARY ==========")
        print(f"Status: {sql_mongo_result['status']}")
        print(f"Tables migrated: {sql_mongo_result['tables_migrated']}")
        print(f"Tables failed: {sql_mongo_result['tables_failed']}")
        print(f"Rows migrated: {sql_mongo_result['rows_migrated']}")

        if sql_mongo_result["errors"]:
            print("\nFirst 5 SQL to MongoDB migration errors:")
            for error in sql_mongo_result["errors"][:5]:
                print(f"  {error['schema_name']}.{error['table_name']}: {error['error']}")

    # ── MongoDB → SQL ────────────────────────────────────────────────────────
    if source_type == "mongodb" and target_type in ["mysql", "postgresql", "mssql"]:
        print("\n========== MONGODB TO SQL MIGRATION ==========")

        mongo_source_connection = manager.mongo_clients["source_database"]
        sql_target_connection = manager.database_engines["target_database"]

        mongo_sql_result = migrate_mongodb_to_sql(
            mongo_client=mongo_source_connection,
            source_database_name=source_database_name,
            target_type=target_type,
            target_engine=sql_target_connection,
            batch_size=1000,
        )

        print("\n========== MONGODB TO SQL MIGRATION SUMMARY ==========")
        print(f"Status: {mongo_sql_result['status']}")
        print(f"Collections migrated: {mongo_sql_result['collections_migrated']}")
        print(f"Collections failed: {mongo_sql_result['collections_failed']}")
        print(f"Documents migrated: {mongo_sql_result['documents_migrated']}")

        if mongo_sql_result["errors"]:
            print("\nFirst 5 MongoDB to SQL migration errors:")
            for error in mongo_sql_result["errors"][:5]:
                print(f"  {error['collection_name']}: {error['error']}")

    # ── SQL → SQL ────────────────────────────────────────────────────────────
    if source_type != "mongodb" and target_type != "mongodb":

        if migration_type["schema"]:
            print("\n========== SCHEMA CONVERSION ==========")

            schema_namespace_statements = build_create_schema_namespace_statements(
                audit_report=audit_report,
                target_type=target_type,
            )

            create_table_statements = build_create_schema_statements(
                audit_report=audit_report,
                source_type=source_type,
                target_type=target_type,
            )

            create_statements = schema_namespace_statements + create_table_statements

            print(f"Generated schema/table statements: {len(create_statements)}")

            target_connection = manager.database_engines["target_database"]

            schema_result = deploy_schema(
                target_type=target_type,
                target_connection=target_connection,
                create_statements=create_statements,
                audit_report=audit_report,
                source_type=source_type,
            )

            print("\n========== SCHEMA DEPLOYMENT SUMMARY ==========")
            print(f"Status: {schema_result['status']}")
            print(f"Tables created: {schema_result['created_tables']}")
            print(f"Tables failed:  {schema_result['failed_tables']}")
            print(f"Constraints applied: {schema_result.get('constraints_applied', 0)}")
            print(f"Foreign keys applied: {schema_result.get('foreign_keys_applied', 0)}")
            print(f"Indexes applied: {schema_result.get('indexes_applied', 0)}")

            if schema_result["errors"]:
                print(f"\nSchema errors ({len(schema_result['errors'])} total, first 5):")
                for error in schema_result["errors"][:5]:
                    print(f"  [{error.get('phase','?')}] {error['error'][:120]}")

        # BUG FIX: data migration block was previously nested inside the
        # schema errors block, so it only ran when there were schema errors.
        if migration_type["data"]:
            print("\n========== DATA MIGRATION ==========")

            source_connection = manager.database_engines["source_database"]
            target_connection = manager.database_engines["target_database"]

            data_result = migrate_data(
                source_type=source_type,
                target_type=target_type,
                source_connection=source_connection,
                target_connection=target_connection,
                audit_report=audit_report,
                batch_size=1000,
            )

            print("\n========== DATA MIGRATION SUMMARY ==========")
            print(f"Status: {data_result['status']}")
            print(f"Tables migrated: {data_result['tables_migrated']}")
            print(f"Tables failed: {data_result['tables_failed']}")
            print(f"Rows migrated: {data_result['rows_migrated']}")

            if data_result["errors"]:
                print("\nFirst 5 data migration errors:")
                for error in data_result["errors"][:5]:
                    print(f"  {error['schema_name']}.{error['table_name']}: {error['error']}")

    # ── Programmable objects ─────────────────────────────────────────────────
    if migration_type["programmable_objects"]:
        print("\n========== PROGRAMMABLE OBJECTS MIGRATION ==========")

        target_connection = (
            manager.mongo_clients["target_database"]
            if target_type == "mongodb"
            else manager.database_engines["target_database"]
        )

        object_result = migrate_programmable_objects(
            source_type=source_type,
            target_type=target_type,
            target_connection=target_connection,
            audit_report=audit_report,
        )

        print(f"Status: {object_result['status']}")
        print(f"Views found: {object_result['views_found']}")
        print(f"Routines found: {object_result['routines_found']}")
        print(f"Triggers found: {object_result['triggers_found']}")
        print(f"Views created: {object_result['views_created']}")
        print(f"Routines created: {object_result['routines_created']}")
        print(f"Triggers created: {object_result['triggers_created']}")
        print(f"Objects failed: {len(object_result['objects_failed'])}")
        print(f"Objects skipped/generated: {len(object_result['objects_skipped'])}")

        # BUG FIX: removed duplicate prints of objects_failed/objects_skipped

        if object_result["objects_failed"]:
            print("\nFirst 5 failed programmable objects:")
            for obj in object_result["objects_failed"][:5]:
                print(f"  {obj['object_type']} - {obj['object_name']}: {obj['error']}")

    print("\n========== MIGRATION COMPLETE ==========")
    print(f"Source: {source_type} -> {source_database_name}")
    print(f"Target: {target_type} -> {target_database_name}")
    print(f"Migration Type: {migration_type['name']}")

    manager.close_all()


if __name__ == "__main__":
    main()
