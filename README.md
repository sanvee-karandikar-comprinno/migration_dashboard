
# Database Migration Dashboard

A production-grade, cross-platform database migration tool built with **Python** and **Streamlit**. Supports schema, data, and programmable object migration across SQL and NoSQL databases with connection pooling and CDC (Change Data Capture).

---

## Supported Migration Paths

| Source ↓ / Target → | MSSQL | MySQL | PostgreSQL | MongoDB |
|---|:---:|:---:|:---:|:---:|
| **MSSQL** | — | ✅ | ✅ | ✅ |
| **MySQL** | ✅ | — | ✅ | ✅ |
| **PostgreSQL** | ✅ | ✅ | — | ✅ |
| **MongoDB** | ✅ | ✅ | ✅ | — |

---

## Features

- **Generalized Architecture** — No hardcoded values. All configuration via `.env` or UI inputs.
- **Connection Pooling** — SQLAlchemy pool (`pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`, `pool_pre_ping`) and MongoDB `maxPoolSize`.
- **Dynamic Auditor** — One auditor for all database types. Collects tables, columns, PKs, FKs, indexes, views, procedures, functions, triggers.
- **Schema Migration** — Automatic type mapping across all SQL databases with proper naming conventions:
  - PostgreSQL: `"schema"."table"` (real schemas via `CREATE SCHEMA`)
  - MySQL: `` `schema_table` `` (flat namespace, schema prefixed)
  - MSSQL: `[schema].[table]` (real schemas)
  - MongoDB: `schema_table` (collection name)
- **Data Migration** — Batched inserts with FK constraint disabling for performance.
- **Programmable Objects** — Views, procedures, functions, triggers translated and deployed automatically.
- **CDC (Change Data Capture)** — Captures incremental changes from SQL sources and applies to MongoDB targets.
- **Incremental Sync** — "Sync Changes" button detects new tables added after initial migration and migrates them without dropping existing data.
- **Target Auto-Creation** — Target database named `<source_db>_migration_target`, dropped and recreated on each full migration for clean state.
- **Reports** — JSON reports saved after each migration with full audit and results.

---

## Architecture

```
migration_dashboard/
├── dashboard.py                  # Streamlit UI — all tabs, sidebar, pipeline
├── .env.example                  # Configuration template
├── requirements.txt              # Python dependencies
│
├── connectors/
│   ├── connection_manager.py     # Connection pooling (SQLAlchemy + PyMongo)
│   └── models.py                 # ServerConnectionConfig, PoolConfig dataclasses
│
├── core/
│   ├── auditor/
│   │   └── dynamic_auditor.py    # Schema audit for all DB types
│   ├── schema/
│   │   ├── type_mapper.py        # Data type mappings (all 6 directions)
│   │   ├── schema_builder.py     # DDL generation with naming conventions
│   │   └── schema_deployer.py    # DDL execution + target DB creation
│   ├── data/
│   │   └── data_migrator.py      # Batch data transfer (SQL → SQL)
│   ├── objects/
│   │   └── object_migrator.py    # Views, procedures, functions, triggers
│   ├── nosql/
│   │   ├── sql_to_mongo_migrator.py   # SQL → MongoDB
│   │   ├── mongo_to_sql_migrator.py   # MongoDB → SQL
│   │   └── mongo_schema_inferer.py    # Infer SQL schema from MongoDB docs
│   └── cdc/
│       ├── cdc_engine.py         # Generic CDC engine with checkpoint
│       ├── base_cdc.py           # Abstract CDC interface
│       ├── mssql_cdc.py          # MSSQL native CDC / trigger fallback
│       ├── postgresql_cdc.py     # PostgreSQL timestamp-based polling
│       ├── mysql_cdc.py          # MySQL timestamp-based polling
│       ├── mongodb_cdc.py        # MongoDB Change Streams
│       └── mongo_applier.py      # Applies CDC events to MongoDB
│
├── reports/                      # Auto-generated migration reports (JSON)
└── tests/
    └── test_core.py              # Unit tests
```

---

## How It Works

### Migration Pipeline

```
Source Connection → Audit → Target DB Creation → Schema Deployment → Data Migration → Object Migration → CDC → Report
```

Each step is visualized in the dashboard with status indicators (✓ success, ✗ failed, ● running, ○ pending, – skipped).

### Connection Pooling

```python
# SQLAlchemy maintains a pool of reusable connections
engine = create_engine(url,
    pool_size=5,        # 5 permanent connections always ready
    max_overflow=10,    # 10 extra connections during peak load
    pool_timeout=30,    # Wait 30s for a connection before error
    pool_recycle=3600,  # Recreate connections after 1 hour (prevents stale)
    pool_pre_ping=True, # Test connection is alive before using it
)

# MongoDB manages its own pool internally
client = MongoClient(host, port, maxPoolSize=20)
```

### CDC (Change Data Capture)

For SQL → MongoDB migrations, CDC detects incremental changes:

```
SQL Source → CDC Adapter (captures INSERT/UPDATE/DELETE) → MongoApplier → MongoDB Target
```

- **MSSQL**: Native transaction log CDC or trigger-based fallback
- **PostgreSQL/MySQL**: Timestamp-based polling on `modifieddate`/`updated_at` columns

---

## Setup & Run

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/migration-dashboard.git
cd migration-dashboard
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your database credentials:

```env
# MSSQL
MSSQL_HOST=localhost
MSSQL_PORT=1433
MSSQL_TRUSTED_CONNECTION=true
MSSQL_DRIVER=ODBC Driver 17 for SQL Server

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USERNAME=root
MYSQL_PASSWORD=yourpassword

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USERNAME=postgres
POSTGRES_PASSWORD=yourpassword

# MongoDB
MONGODB_HOST=localhost
MONGODB_PORT=27017

# Pool Settings
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600
```

### 3. Create virtual environment and install dependencies

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
```

### 4. Run the dashboard

```bash
streamlit run dashboard.py
```

Opens at **http://localhost:8501**

---

## Usage

1. **Select Source Type** (e.g., MSSQL) → Enter host/port → Check "Windows Auth" if needed → Click **Connect Source**
2. **Select Database** from the dropdown that appears
3. **Select Target Type** (e.g., MySQL) → Enter credentials → Click **Connect Target**
4. **Choose Migration Mode**:
   - `Schema Only` — Creates tables in target
   - `Schema + Data` — Creates tables + migrates all rows
   - `Full Migration` — Schema + Data + Programmable Objects + CDC
5. Click **▶ Run Migration**
6. After completion, click **🔄 Sync Changes** to detect and migrate new tables incrementally

---

## Naming Conventions

| Source Schema.Table | PostgreSQL Target | MySQL Target | MongoDB Target |
|---|---|---|---|
| `HumanResources.Employee` | `"humanresources"."employee"` | `` `humanresources_employee` `` | `humanresources_employee` |
| `dbo.Product` | `"public"."product"` | `` `product` `` | `product` |
| `Sales.Order` | `"sales"."order"` | `` `sales_order` `` | `sales_order` |

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| SQLAlchemy for SQL connections | Unified API across MSSQL/MySQL/PostgreSQL with built-in pooling |
| `pool_pre_ping=True` | Prevents "connection reset" errors in long-running dashboards |
| `pool_recycle=3600` | Recreates connections hourly to prevent "server has gone away" |
| Target DB dropped on full migration | Ensures clean state, prevents duplicate entry errors |
| Stub objects for complex T-SQL | Ensures all objects exist in target even if syntax can't be fully translated |
| Timestamp-based CDC for PostgreSQL/MySQL | Works without requiring server-side replication configuration |
| Batch inserts (1000 rows default) | 10-100x faster than row-by-row; prevents memory issues |

---

## Limitations

- **Programmable Objects**: Complex T-SQL procedures/functions with `@variables`, `CURSOR`, `EXEC()` are deployed as stubs (functional placeholders). Full conversion requires manual review.
- **CDC for PostgreSQL/MySQL**: Uses timestamp polling (not true log-based CDC). Requires tables to have a `modifieddate`/`updated_at` column for change detection.
- **MongoDB → SQL**: Deeply nested documents are flattened. Arrays stored as JSON strings.
- **MongoDB → MongoDB**: Architecture is ready but not yet implemented.

---

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Dashboard UI |
| `sqlalchemy` | SQL database connections with pooling |
| `pyodbc` | MSSQL ODBC driver |
| `mysql-connector-python` | MySQL driver |
| `psycopg2-binary` | PostgreSQL driver |
| `pymongo` | MongoDB driver |
| `python-dotenv` | Load `.env` configuration |
| `pandas` | Data display in dashboard |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## License

MIT
=======
# migration_dashboard
Automated database migration framework supporting MSSQL, MySQL, PostgreSQL, MongoDB with schema conversion, data migration, CDC, validation, reporting, and an interactive dashboard for database modernization.

