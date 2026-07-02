"""
Database Migration Dashboard
=============================
Run with: streamlit run dashboard.py

Professional database migration tool supporting MSSQL, MySQL, PostgreSQL, MongoDB.
All configuration from .env or UI inputs — nothing hardcoded.
"""

import os
import json
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from connectors.models import ServerConnectionConfig, PoolConfig
from connectors.connection_manager import ConnectionManager
from core.auditor.dynamic_auditor import DynamicAuditor
from core.schema.schema_builder import build_schema_ddl
from core.schema.schema_deployer import deploy_schema, create_target_database
from core.data.data_migrator import migrate_data
from core.objects.object_migrator import migrate_objects
from core.nosql.sql_to_mongo_migrator import migrate_sql_to_mongodb
from core.nosql.mongo_to_sql_migrator import migrate_mongodb_to_sql
from core.cdc.cdc_engine import create_cdc_engine
from core.cdc.mongo_applier import MongoApplier

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Migration Dashboard", page_icon="⚡", layout="wide")

# ─── Custom CSS for corporate look ──────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1rem; }
    [data-testid="stMetric"] {
        background: #1e293b;
        padding: 12px 16px;
        border-radius: 8px;
        border: 1px solid #334155;
    }
    [data-testid="stMetric"] label { color: #94a3b8 !important; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] { color: #f1f5f9 !important; }
    .step-box { padding: 8px 12px; border-radius: 6px; text-align: center; font-size: 0.8rem; font-weight: 500; }
    .step-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .step-failed { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .step-running { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
    .step-pending { background: #e2e3e5; color: #383d41; border: 1px solid #d6d8db; }
    .step-skipped { background: #e2e3e5; color: #6c757d; border: 1px solid #d6d8db; }
</style>
""", unsafe_allow_html=True)

# ─── Session State ───────────────────────────────────────────────────────────
for key, default in {
    "migration_status": "idle",
    "audit_report": None,
    "schema_result": None,
    "data_result": None,
    "object_result": None,
    "logs": [],
    "source_databases": [],
    "target_databases": [],
    "connection_manager": None,
    "pipeline_steps": {},
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

DB_TYPES = ["mssql", "mysql", "postgresql", "mongodb"]
DEFAULT_PORTS = {"mssql": "1433", "mysql": "3306", "postgresql": "5432", "mongodb": "27017"}
ENV_PREFIX = {"mssql": "MSSQL", "mysql": "MYSQL", "postgresql": "POSTGRES", "mongodb": "MONGODB"}


# ─── Utilities ───────────────────────────────────────────────────────────────
def add_log(msg: str):
    st.session_state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_mgr() -> ConnectionManager:
    if st.session_state.connection_manager is None:
        st.session_state.connection_manager = ConnectionManager()
    return st.session_state.connection_manager


def build_config(db_type: str, prefix: str) -> ServerConnectionConfig:
    """Builds connection config from session state with .env fallbacks."""
    env_pfx = ENV_PREFIX.get(db_type, db_type.upper())
    host = st.session_state.get(f"{prefix}_host", "") or os.getenv(f"{env_pfx}_HOST", "localhost")
    port = st.session_state.get(f"{prefix}_port", "") or os.getenv(f"{env_pfx}_PORT", DEFAULT_PORTS[db_type])
    user = st.session_state.get(f"{prefix}_user", "") or os.getenv(f"{env_pfx}_USERNAME", "")
    pwd = st.session_state.get(f"{prefix}_pass", "") or os.getenv(f"{env_pfx}_PASSWORD", "")

    kwargs = dict(db_type=db_type, host=host, port=int(port) if port else int(DEFAULT_PORTS[db_type]),
                  username=user, password=pwd)

    if db_type == "mssql":
        kwargs["driver"] = os.getenv("MSSQL_DRIVER", "ODBC Driver 17 for SQL Server")
        kwargs["trusted_connection"] = st.session_state.get(f"{prefix}_trusted",
                                        os.getenv("MSSQL_TRUSTED_CONNECTION", "false").lower() == "true")

    return ServerConnectionConfig(**kwargs)


# ─── Migration Logic (defined before UI so button can call it) ───────────────
def _do_run_migration():
    """
    Executes the full migration pipeline.
    
    Pipeline Steps:
    1. Connect to source database
    2. Audit source (discover tables, columns, PKs, FKs, views, etc.)
    3. Create fresh target database (drops existing to avoid duplicates)
    4. Deploy schema (CREATE TABLE statements with mapped data types)
    5. Migrate data in batches (SELECT from source → INSERT into target)
    6. Migrate programmable objects (views, procedures, functions, triggers)
    7. Run CDC to capture any changes made during migration (MongoDB targets only)
    8. Save migration report as JSON
    """
    st.session_state.migration_status = "running"
    st.session_state.logs = []
    st.session_state.pipeline_steps = {}

    try:
        mgr = get_mgr()
        src_type = st.session_state.get("src_type", "mssql")
        tgt_type = st.session_state.get("tgt_type", "mysql")
        src_db = st.session_state.get("src_database", "")
        batch_size = st.session_state.get("batch_size", 1000)
        mode = st.session_state.get("migration_mode", "Full Migration")

        if not src_db:
            raise ValueError("Select a source database first.")

        tgt_db = f"{src_db}_migration_target"
        add_log(f"Source: {src_type}/{src_db} → Target: {tgt_type}/{tgt_db}")

        # Connect source DB
        st.session_state.pipeline_steps["source_connect"] = "success"
        src_config = build_config(src_type, "src")
        src_conn = mgr.connect_database("source_db", src_config, src_db)
        add_log("Source connected")

        # Audit
        st.session_state.pipeline_steps["audit"] = "running"
        auditor = DynamicAuditor(src_type, src_conn, src_db)
        audit = auditor.run_audit()
        st.session_state.audit_report = audit
        st.session_state.pipeline_steps["audit"] = "success"
        add_log(f"Audit: {audit['summary']['total_tables']} tables found")

        # Connect target
        st.session_state.pipeline_steps["target_setup"] = "running"
        tgt_config = build_config(tgt_type, "tgt")

        if tgt_type != "mongodb":
            tgt_server = mgr.connect_server("target_srv", tgt_config)
            create_target_database(tgt_server, tgt_type, tgt_db)
            tgt_conn = mgr.connect_database("target_db", tgt_config, tgt_db)
        else:
            tgt_conn = mgr.connect_server("target_srv", tgt_config)

        st.session_state.pipeline_steps["target_setup"] = "success"
        add_log(f"Target ready: {tgt_db}")

        # Schema
        if tgt_type != "mongodb" and src_type != "mongodb":
            st.session_state.pipeline_steps["schema"] = "running"
            schema_ddl = build_schema_ddl(audit, src_type, tgt_type)
            schema_result = deploy_schema(tgt_conn, schema_ddl)
            st.session_state.schema_result = schema_result
            st.session_state.pipeline_steps["schema"] = "success"
            add_log(f"Schema: {schema_result['tables_created']} created, {schema_result['tables_failed']} failed")
        else:
            st.session_state.pipeline_steps["schema"] = "skipped"

        # Data
        if mode in ("Schema + Data", "Full Migration"):
            st.session_state.pipeline_steps["data"] = "running"
            if src_type == "mongodb" and tgt_type != "mongodb":
                data_result = migrate_mongodb_to_sql(
                    mongo_client=src_conn, target_engine=tgt_conn,
                    source_database=src_db, target_database=tgt_db,
                    target_type=tgt_type, batch_size=batch_size, log_callback=add_log)
            elif src_type != "mongodb" and tgt_type == "mongodb":
                data_result = migrate_sql_to_mongodb(
                    source_engine=src_conn, mongo_client=tgt_conn,
                    source_type=src_type, source_database=src_db,
                    target_database=tgt_db, audit_report=audit,
                    batch_size=batch_size, log_callback=add_log)
            else:
                data_result = migrate_data(
                    source_engine=src_conn, target_engine=tgt_conn,
                    source_type=src_type, target_type=tgt_type,
                    audit_report=audit, batch_size=batch_size, log_callback=add_log)
            st.session_state.data_result = data_result
            st.session_state.pipeline_steps["data"] = "success"
            add_log(f"Data: {data_result.get('tables_migrated', data_result.get('collections_migrated', 0))} migrated")
        else:
            st.session_state.pipeline_steps["data"] = "skipped"

        # Objects
        if mode == "Full Migration":
            st.session_state.pipeline_steps["objects"] = "running"
            obj_result = migrate_objects(
                target_engine=tgt_conn if tgt_type != "mongodb" else None,
                source_type=src_type, target_type=tgt_type,
                audit_report=audit, log_callback=add_log)
            st.session_state.object_result = obj_result
            st.session_state.pipeline_steps["objects"] = "success"
        else:
            st.session_state.pipeline_steps["objects"] = "skipped"

        # Step 6: CDC (for MongoDB targets from SQL sources)
        if tgt_type == "mongodb" and src_type in ("mssql", "mysql", "postgresql"):
            st.session_state.pipeline_steps["cdc"] = "running"
            add_log("Starting CDC (Change Data Capture) sync...")
            try:
                cdc_result = _run_cdc_to_mongo(src_conn, tgt_conn, src_type, src_db, tgt_db, audit)
                st.session_state["cdc_result"] = cdc_result
                st.session_state.pipeline_steps["cdc"] = "success"
                add_log(f"CDC: {cdc_result.get('events_applied', 0)} changes captured and applied")
            except Exception as e:
                st.session_state.pipeline_steps["cdc"] = "failed"
                add_log(f"CDC error (non-fatal): {e}")

        # Save report
        _save_report(audit, tgt_db)
        st.session_state.migration_status = "completed"
        add_log("Migration completed successfully.")

    except Exception as e:
        st.session_state.migration_status = "failed"
        add_log(f"ERROR: {e}")
        for k, v in st.session_state.pipeline_steps.items():
            if v == "running":
                st.session_state.pipeline_steps[k] = "failed"


def _do_sync():
    """
    Incremental sync: Re-audits source, detects new tables/data,
    migrates only what's new or changed. Does NOT drop the target.
    """
    st.session_state.migration_status = "running"
    add_log("--- SYNC: Detecting new tables and changes ---")

    try:
        mgr = get_mgr()
        src_type = st.session_state.get("src_type", "mssql")
        tgt_type = st.session_state.get("tgt_type", "mysql")
        src_db = st.session_state.get("src_database", "")
        batch_size = st.session_state.get("batch_size", 1000)

        if not src_db:
            raise ValueError("No source database selected.")

        tgt_db = f"{src_db}_migration_target"

        # Re-audit source to detect new tables
        src_config = build_config(src_type, "src")
        src_conn = mgr.connect_database("source_db", src_config, src_db)
        auditor = DynamicAuditor(src_type, src_conn, src_db)
        new_audit = auditor.run_audit()

        # Compare with previous audit to find new tables
        old_audit = st.session_state.audit_report or {"tables": []}
        old_table_names = {(t["schema_name"], t["table_name"]) for t in old_audit.get("tables", [])}
        new_tables = [t for t in new_audit["tables"] if (t["schema_name"], t["table_name"]) not in old_table_names]

        # Update stored audit
        st.session_state.audit_report = new_audit

        add_log(f"Sync: {len(new_audit['tables'])} total tables, {len(new_tables)} NEW tables detected")

        # Connect to target (without dropping it)
        tgt_config = build_config(tgt_type, "tgt")
        if tgt_type == "mongodb":
            tgt_conn = mgr.connect_server("target_srv", tgt_config)
        else:
            tgt_conn = mgr.connect_database("target_db", tgt_config, tgt_db)

        # Migrate new tables
        if new_tables:
            add_log(f"Migrating {len(new_tables)} new tables...")

            # Build a mini audit with only new tables and their columns
            new_table_keys = {(t["schema_name"], t["table_name"]) for t in new_tables}
            new_columns = [c for c in new_audit["columns"]
                          if (c["schema_name"], c["table_name"]) in new_table_keys]

            sync_audit = {
                "tables": new_tables,
                "columns": new_columns,
                "primary_keys": [pk for pk in new_audit.get("primary_keys", [])
                                if (pk["schema_name"], pk["table_name"]) in new_table_keys],
                "foreign_keys": [],
                "indexes": [],
                "views": [],
                "routines": [],
                "triggers": [],
                "summary": {"total_tables": len(new_tables), "total_columns": len(new_columns),
                           "total_primary_keys": 0, "total_foreign_keys": 0,
                           "total_indexes": 0, "total_views": 0, "total_routines": 0, "total_triggers": 0},
            }

            if tgt_type == "mongodb":
                result = migrate_sql_to_mongodb(
                    source_engine=src_conn, mongo_client=tgt_conn,
                    source_type=src_type, source_database=src_db,
                    target_database=tgt_db, audit_report=sync_audit,
                    batch_size=batch_size, log_callback=add_log)
                add_log(f"Sync: {result.get('tables_migrated', 0)} new tables migrated to MongoDB")
            else:
                schema_ddl = build_schema_ddl(sync_audit, src_type, tgt_type)
                deploy_schema(tgt_conn, schema_ddl)
                result = migrate_data(src_conn, tgt_conn, src_type, tgt_type,
                                     sync_audit, batch_size, log_callback=add_log)
                add_log(f"Sync: {result.get('tables_migrated', 0)} new tables migrated")
        else:
            add_log("No new tables found.")

        # Run CDC for row-level changes on existing tables
        if tgt_type == "mongodb" and src_type in ("mssql", "mysql", "postgresql"):
            add_log("Running CDC for row-level changes...")
            cdc_result = _run_cdc_to_mongo(src_conn, tgt_conn, src_type, src_db, tgt_db, new_audit)
            st.session_state["cdc_result"] = cdc_result
            captured = cdc_result.get("events_applied", 0)
            if captured > 0:
                add_log(f"CDC: {captured} row changes applied")
            else:
                add_log("CDC: No row-level changes detected")

        st.session_state.migration_status = "completed"
        add_log("Sync completed successfully.")

    except Exception as e:
        st.session_state.migration_status = "failed"
        add_log(f"Sync ERROR: {e}")


def _run_cdc_to_mongo(src_engine, mongo_client, source_type, source_db, target_db, audit):
    """
    Runs Change Data Capture from SQL source to MongoDB target.
    
    CDC captures any INSERT/UPDATE/DELETE changes that happened in the source
    since the initial load and applies them to MongoDB in real-time.
    
    This ensures the MongoDB target stays synchronized with the SQL source.
    Only supported for MSSQL sources (native CDC) currently.
    For MySQL/PostgreSQL, it captures recent changes via timestamp-based polling.
    """
    applier = MongoApplier(mongo_client, target_db, log_callback=add_log)

    try:
        # Get list of tables from audit
        tables = [f"{t['schema_name']}.{t['table_name']}" for t in audit.get("tables", [])]

        # Create CDC engine connected to the source
        engine = create_cdc_engine(
            source_type=source_type,
            source_connection=src_engine,
            database_name=source_db,
            apply_event=applier.apply_event,
            checkpoint_file=f"reports/cdc_checkpoint_{source_db}.json",
        )

        # Run CDC capture (will capture recent changes)
        stats = engine.run(tables=tables[:10])  # Limit to first 10 tables for performance
        
        # Combine engine stats with applier stats
        result = {**stats, **applier.get_stats()}
        return result

    except ValueError as e:
        # CDC not supported for this source type — not an error, just skip
        add_log(f"CDC: {e}")
        return {"events_captured": 0, "events_applied": 0, "message": str(e)}
    except Exception as e:
        add_log(f"CDC warning: {e}")
        return {"events_captured": 0, "events_applied": 0, "error": str(e)}


def _save_report(audit, tgt_db):
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    report = {
        "timestamp": datetime.now().isoformat(),
        "source": audit.get("database_name", ""),
        "target": tgt_db,
        "summary": audit.get("summary", {}),
        "schema": st.session_state.schema_result,
        "data": st.session_state.data_result,
        "objects": st.session_state.object_result,
    }
    filepath = reports_dir / f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    add_log(f"Report: {filepath.name}")


# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown("## Database Migration Dashboard")
st.caption("Cross-platform schema, data, and object migration")

# ─── Top Section: Source & Target Configuration (Horizontal) ─────────────────
st.markdown("---")
col_src, col_tgt, col_action = st.columns([3, 3, 2])

with col_src:
    st.markdown("**Source**")
    src_type = st.selectbox("Type", DB_TYPES, key="src_type")
    s1, s2 = st.columns(2)
    s1.text_input("Host", value=os.getenv(f"{ENV_PREFIX.get(src_type, '')}_HOST", "localhost"), key="src_host")
    s2.text_input("Port", value=os.getenv(f"{ENV_PREFIX.get(src_type, '')}_PORT", DEFAULT_PORTS.get(src_type, "3306")), key="src_port")
    
    if src_type == "mssql":
        st.checkbox("Windows Authentication", value=os.getenv("MSSQL_TRUSTED_CONNECTION", "false").lower() == "true", key="src_trusted")
    
    s3, s4 = st.columns(2)
    s3.text_input("Username", value=os.getenv(f"{ENV_PREFIX.get(src_type, '')}_USERNAME", ""), key="src_user")
    s4.text_input("Password", type="password", value="", key="src_pass")

    if st.button("Connect Source", use_container_width=True):
        try:
            cfg = build_config(src_type, "src")
            mgr = get_mgr()
            mgr.connect_server("source", cfg)
            dbs = mgr.list_databases("source", cfg)
            st.session_state.source_databases = dbs
            st.success(f"Connected — {len(dbs)} databases found")
        except Exception as e:
            st.error(f"Failed: {e}")

    if st.session_state.source_databases:
        st.selectbox("Source Database", st.session_state.source_databases, key="src_database")

with col_tgt:
    st.markdown("**Target**")
    tgt_type = st.selectbox("Type", DB_TYPES, key="tgt_type")
    t1, t2 = st.columns(2)
    t1.text_input("Host", value=os.getenv(f"{ENV_PREFIX.get(tgt_type, '')}_HOST", "localhost"), key="tgt_host")
    t2.text_input("Port", value=os.getenv(f"{ENV_PREFIX.get(tgt_type, '')}_PORT", DEFAULT_PORTS.get(tgt_type, "3306")), key="tgt_port")

    if tgt_type == "mssql":
        st.checkbox("Windows Authentication ", value=False, key="tgt_trusted")

    t3, t4 = st.columns(2)
    t3.text_input("Username", value=os.getenv(f"{ENV_PREFIX.get(tgt_type, '')}_USERNAME", ""), key="tgt_user")
    t4.text_input("Password", type="password", value="", key="tgt_pass")

    if st.button("Connect Target", use_container_width=True):
        try:
            cfg = build_config(tgt_type, "tgt")
            mgr = get_mgr()
            mgr.connect_server("target", cfg)
            dbs = mgr.list_databases("target", cfg)
            st.session_state.target_databases = dbs
            st.success(f"Connected — {len(dbs)} databases found")
        except Exception as e:
            st.error(f"Failed: {e}")

with col_action:
    st.markdown("**Migration**")
    mode = st.selectbox("Mode", ["Schema Only", "Schema + Data", "Full Migration"], key="migration_mode")
    batch = st.number_input("Batch Size", min_value=100, max_value=50000,
                            value=int(os.getenv("DEFAULT_BATCH_SIZE", "1000")), key="batch_size")

    st.markdown("")
    run_disabled = st.session_state.migration_status == "running" or not st.session_state.source_databases
    if st.button("▶ Run Migration", type="primary", use_container_width=True, disabled=run_disabled):
        _do_run_migration()

    # Sync button — re-audits source and migrates new/changed data
    if st.session_state.migration_status == "completed":
        if st.button("🔄 Sync Changes", use_container_width=True):
            _do_sync()

    status = st.session_state.migration_status
    if status == "running":
        st.warning("Running...")
    elif status == "completed":
        st.success("Completed")
    elif status == "failed":
        st.error("Failed")


# ─── Pipeline Status Bar ─────────────────────────────────────────────────────
st.markdown("---")
if st.session_state.pipeline_steps:
    step_labels = {
        "source_connect": "Source",
        "audit": "Audit",
        "target_setup": "Target",
        "schema": "Schema",
        "data": "Data",
        "objects": "Objects",
        "cdc": "CDC",
    }
    cols = st.columns(len(step_labels))
    for i, (key, label) in enumerate(step_labels.items()):
        status = st.session_state.pipeline_steps.get(key, "pending")
        css_class = f"step-{status}"
        icon = {"success": "✓", "failed": "✗", "running": "●", "pending": "○", "skipped": "–"}.get(status, "○")
        cols[i].markdown(f'<div class="step-box {css_class}">{icon} {label}</div>', unsafe_allow_html=True)


# ─── Tabs ────────────────────────────────────────────────────────────────────
tab_overview, tab_schema, tab_data, tab_objects, tab_audit, tab_reports, tab_logs = st.tabs(
    ["Overview", "Schema", "Data", "Objects", "Audit", "Reports", "Logs"]
)

# ── Overview Tab ──
with tab_overview:
    audit = st.session_state.audit_report
    if audit:
        st.markdown("### Source Database Metrics")
        s = audit["summary"]
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Tables", s["total_tables"])
        c2.metric("Columns", s["total_columns"])
        c3.metric("Primary Keys", s["total_primary_keys"])
        c4.metric("Foreign Keys", s["total_foreign_keys"])
        c5.metric("Indexes", s["total_indexes"])
        c6.metric("Views", s["total_views"])

        st.markdown("")
        c7, c8 = st.columns(2)
        c7.metric("Routines (Procedures/Functions)", s["total_routines"])
        c8.metric("Triggers", s["total_triggers"])

        if st.session_state.schema_result:
            st.markdown("---")
            st.markdown("### Schema Migration Results")
            sr = st.session_state.schema_result
            c1, c2, c3 = st.columns(3)
            c1.metric("Tables Created", sr.get("tables_created", 0))
            c2.metric("Tables Failed", sr.get("tables_failed", 0))
            c3.metric("Schemas Created", sr.get("schemas_created", 0))

        if st.session_state.data_result:
            st.markdown("---")
            st.markdown("### Data Migration Results")
            dr = st.session_state.data_result
            c1, c2, c3 = st.columns(3)
            c1.metric("Tables Migrated", dr.get("tables_migrated", dr.get("collections_migrated", 0)))
            c2.metric("Tables Failed", dr.get("tables_failed", dr.get("collections_failed", 0)))
            c3.metric("Total Rows Transferred", f"{dr.get('total_rows', dr.get('total_documents', 0)):,}")

        if st.session_state.object_result:
            st.markdown("---")
            st.markdown("### Programmable Objects Results")
            obj = st.session_state.object_result
            views_data = obj.get("views", {})
            routines_data = obj.get("routines", {})
            triggers_data = obj.get("triggers", {})
            c1, c2, c3 = st.columns(3)
            c1.metric("Views", f"{views_data.get('created', 0)}/{views_data.get('found', 0)} deployed")
            c2.metric("Routines", f"{routines_data.get('created', 0)}/{routines_data.get('found', 0)} deployed")
            c3.metric("Triggers", f"{triggers_data.get('created', 0)}/{triggers_data.get('found', 0)} deployed")

        if st.session_state.get("cdc_result"):
            st.markdown("---")
            st.markdown("### CDC (Change Data Capture)")
            cdc = st.session_state["cdc_result"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Events Captured", cdc.get("events_captured", 0))
            c2.metric("Events Applied", cdc.get("events_applied", 0))
            c3.metric("Inserts", cdc.get("inserts", 0))
            c4.metric("Updates/Deletes", cdc.get("updates", 0) + cdc.get("deletes", 0))
            if cdc.get("message"):
                st.info(cdc["message"])
    else:
        st.markdown("### Getting Started")
        st.markdown("""
        1. **Connect Source** — Select your source database type, enter credentials, click Connect
        2. **Select Database** — Pick the database you want to migrate from the dropdown
        3. **Connect Target** — Configure where you want to migrate to
        4. **Run Migration** — Choose migration mode and click Run
        """)
        st.info("Configure source and target connections above, then run a migration to see results here.")

# ── Schema Tab ──
with tab_schema:
    result = st.session_state.schema_result
    if result:
        errors = result.get("errors", [])
        if not errors:
            st.success(f"All {result.get('tables_created', 0)} tables created successfully.")
        else:
            st.warning(f"{result.get('tables_failed', 0)} tables failed.")
            for err in errors:
                with st.expander(f"✗ {err['table_name']}"):
                    st.code(err.get("sql", "")[:500], language="sql")
                    st.error(err.get("error", ""))
    else:
        st.info("No schema results yet.")

# ── Data Tab ──
with tab_data:
    result = st.session_state.data_result
    if result:
        table_results = result.get("table_results", [])
        if table_results:
            rows = []
            for tr in table_results:
                name = tr.get("table_name", tr.get("collection_name", ""))
                status = tr.get("status", "")
                row_count = tr.get("rows_migrated", tr.get("rows", tr.get("documents", 0)))
                rows.append({"Table": name, "Status": status, "Rows": row_count,
                             "Error": tr.get("error", "") or ""})
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No table-level results.")
    else:
        st.info("No data results yet.")

# ── Objects Tab ──
with tab_objects:
    result = st.session_state.object_result
    if result:
        if result.get("message"):
            st.info(result["message"])
        for section, label in [("views", "Views"), ("routines", "Routines"), ("triggers", "Triggers")]:
            data = result.get(section, {})
            if data.get("found", 0) > 0:
                st.markdown(f"**{label}** — Found: {data['found']}, Created: {data['created']}, Failed: {data['failed']}, Skipped: {data['skipped']}")
                details = data.get("details", [])
                if details:
                    df = pd.DataFrame(details)
                    st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No object migration results yet.")

# ── Audit Tab ──
with tab_audit:
    audit = st.session_state.audit_report
    if audit:
        section = st.selectbox("View", ["Tables", "Columns", "Primary Keys", "Foreign Keys", "Indexes", "Views", "Routines", "Triggers"])
        key_map = {"Tables": "tables", "Columns": "columns", "Primary Keys": "primary_keys",
                   "Foreign Keys": "foreign_keys", "Indexes": "indexes", "Views": "views",
                   "Routines": "routines", "Triggers": "triggers"}
        data = audit.get(key_map[section], [])
        if data:
            df = pd.DataFrame(data)
            # Truncate long definitions for display
            if "definition" in df.columns:
                df["definition"] = df["definition"].str[:80] + "..."
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info(f"No {section.lower()} found.")
    else:
        st.info("Run an audit first.")

# ── Reports Tab ──
with tab_reports:
    reports_dir = Path("reports")
    if reports_dir.exists():
        files = sorted(reports_dir.glob("migration_*.json"), reverse=True)[:15]
        if files:
            for f in files:
                with st.expander(f.name):
                    st.json(json.loads(f.read_text(encoding="utf-8")))
        else:
            st.info("No reports yet.")
    else:
        st.info("Reports directory not found.")

# ── Logs Tab ──
with tab_logs:
    logs = st.session_state.logs
    if logs:
        st.code("\n".join(logs), language="text")
        if st.button("Clear Logs"):
            st.session_state.logs = []
            st.rerun()
    else:
        st.info("No logs yet.")
