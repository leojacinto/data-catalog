# ServiceNow Workflow Data Fabric - Banking Demo

Demonstrates ServiceNow WDF as a **meta-catalog** across three data sources:
- **Snowflake** - front-office risk data warehouse (trades, positions, P&L)
- **Neon PostgreSQL** - middle-office reconciliation database (budget vs actual, variance)
- **ServiceNow ZCC** - live operational data (forecast, variance tasks, expense events)

**Regulatory story:** Australian bank demonstrating APRA CPG 235 / BCBS 239 compliance: data lineage, classification, ownership, and quality checks across all sources, discoverable in one governed catalog.

---

## Prerequisites

### ServiceNow

- Instance on the **Australia release** or later with the **Workflow Data Fabric** plugin activated (`sn_dcg_core`, `sn_dcg_cc`)
- The following roles assigned to your user:
  - `admin` - required to configure connections and run collectors
  - `df_connection_admin` - required to create and manage zero copy connections in Connect Hub
  - `df_data_steward` - required to create and manage Data Interfaces in Data Workbench
  - `data_product_admin` - required to create, update, and publish Data Products
  - `data_product_user` - required for consumers querying published Data Products
- A **MID Server** installed, running, and validated on the instance (see MID Server section below)
- The Neon metadata collector connector (`catalog-postgresql`) available under Connect Hub
- Optional: SNOWSK8S compute provisioned on the instance for the Snowflake KOS collector. If not provisioned (common on PDIs), use `sn_snowflake_catalog_ingest.py` instead.

> **Note:** Build and test in a development or sub-production instance first. Use an update set to promote to production.

### Snowflake

- A Snowflake account with admin or `SYSADMIN` privileges
- A running virtual warehouse (default: `COMPUTE_WH`)
- Privileges to create databases, schemas, tags, and Data Metric Functions
- Snowflake Horizon enabled (available on Enterprise edition and above) for tags and DMFs
- Account locator noted (format: `<orgname>-<accountname>`, e.g. `abc123-xy12345`)

### Neon PostgreSQL

- A [Neon](https://neon.tech) project created (free tier is sufficient)
- Connection string with `sslmode=require`
- The default `neondb_owner` user has full privileges on the `neondb` database
- **Important:** Create a second database named `neondb_owner` on the project. The ServiceNow PostgreSQL collector calls `getAllDatabases()` on connect and defaults to a database matching the username - this prevents a connection error.

### Python

```
pip install snowflake-connector-python psycopg2-binary
```

Requires Python 3.9+.

---

## Setup

1. Copy `.env.example` to `.env` and fill in all values
2. Source the env file: `export $(grep -v '^#' .env | xargs)`

---

## Run Order

| Step | Script / Action | What it does |
|------|----------------|-------------|
| 1 | `neon_base_setup.py` | Creates and seeds Neon base tables: `dim_*`, `monthly_variance_detail`, `summary_variance`, `VARIANCE_BASELINE_V` |
| 2 | `neon_setup.py` | Creates lineage views on top of base tables: `vw_budget_variance_detail`, `vw_budget_anomalies` |
| 3 | `snowflake_setup.py` | Creates `APRA_RISK_DW.RISK` schema: tables, views, seed data |
| 4 | `snowflake_catalog.py` | Adds Snowflake Horizon tags, column-level sensitivity, DMFs, object comments |
| 5 | UI - ZCC setup | Configure Neon zero-copy connection and map data fabric tables in Connect Hub (see below) |
| 6 | `sn_govern.py` | Creates SN domains, glossary terms, enriches Neon asset descriptions |
| 7 | `sn_snowflake_catalog_ingest.py` | Injects Snowflake assets into SN Data Catalog (use if SNOWSK8S compute is not provisioned) |

---

## Zero Copy Connector (ZCC) Setup

The ZCC tables (`x_snc_forecast_v_0_*`) are predefined data fabric tables that ship with the **Forecast Variance** scoped app (`x_snc_forecast_v_0`). They must be connected to your Neon source through Connect Hub.

### Required role

`df_connection_admin` - required to create and manage zero copy connections.

### Step 1 - Create the Neon connection

1. Navigate to **All -> Workflow Data Fabric -> Connect Hub**
2. Click **New Connection**
3. Select connector: **PostgreSQL** (listed under Community connectors)
4. Fill in connection details:
   - **Connection name:** `Neon Forecast DB`
   - **Host:** your Neon endpoint (from `NEON_HOST` in `.env`)
   - **Port:** `5432`
   - **Database:** `neondb`
   - **Username / Password:** from `NEON_USER` / `NEON_PASSWORD` in `.env`
   - **SSL mode:** `require`
5. Click **Test Connection** - confirm it returns success
6. Click **Save**
7. Grant access to your data steward user via the **Access** tab

### Step 2 - Map the data fabric tables

For each of the four tables below, repeat the following:

1. Navigate to the scoped app table list: **All -> Forecast Variance** (or search `x_snc_forecast_v_0` in the navigator)
2. Open the table record and click **Configure Data Source**
3. Select your `Neon Forecast DB` connection
4. Select the corresponding source table from Neon (column names map 1:1)
5. Save

| ServiceNow table | Neon source table | Description |
|-----------------|------------------|-------------|
| `x_snc_forecast_v_0_df_mv_detail` | `monthly_variance_detail` | Budget vs actual variance detail with ML anomaly flags |
| `x_snc_forecast_v_0_df_sv` | `summary_variance` | Aggregated variance by cost centre and period |
| `x_snc_forecast_v_0_variance_task` | (ServiceNow native) | Remediation tasks - no ZCC mapping needed |
| `x_snc_forecast_v_0_expense_transaction_event` | (ServiceNow native) | Expense events - no ZCC mapping needed |

> **Note:** `variance_task` and `expense_transaction_event` are ServiceNow-native tables. Only `df_mv_detail` and `df_sv` require external ZCC mapping to Neon.

### Step 3 - Verify

1. Navigate to **All -> x_snc_forecast_v_0_df_mv_detail_list.do**
2. Confirm rows are returned live from Neon (no data is stored in ServiceNow)

---

## MID Server

The `mid-server/` directory is gitignored. To set up:
1. Download the MID Server zip from your SN instance (`mid_server_download_ui.do`)
2. Extract to `mid-server/`
3. Edit `mid-server/agent/config.xml` and set `url`, `mid.instance.username`, `mid.instance.password`
4. Start: `bash mid-server/agent/start-macos.sh`

**KOS bundle notes:**
- All `kos-bundle-*.jar` files must be at matching versions (check `ecc_agent_jar` table)
- `kos-bundle-d.jar` and `kos-bundle-e.jar`: `resources.txt` must be empty. The split Snowflake JDBC jar entries cause `ExceptionInInitializerError` with the PostgreSQL collector.
- The PostgreSQL JDBC driver is bundled inside the KOS collectors; do not add a separate jar to `extlib/`

---

## Snowflake Collector Note

The KOS `SnowflakeCollector` runs on `SNOWSK8S` (ServiceNow hosted compute), not via MID. If SNOWSK8S is not provisioned on your instance (common on PDIs), run `sn_snowflake_catalog_ingest.py` to manually inject Snowflake assets into the catalog with full descriptions and domain assignments.

---

## Demo Script

See `HOW-TO-DEMO.md` for the full 15-minute demo walkthrough.

---

## Planned Extensions

- **AWS Glue Data Catalog** - data lake layer (raw trade events -> Glue ETL -> Snowflake TRADE), creates cross-system lineage completing the full ingestion chain
