# ServiceNow Workflow Data Fabric - Banking Demo

Demonstrates ServiceNow WDF as a **meta-catalog** across three data sources:
- **Snowflake** - front-office risk data warehouse (trades, positions, P&L)
- **Neon PostgreSQL** - middle-office reconciliation database (budget vs actual, variance)
- **ServiceNow ZCC** - live operational data (forecast, variance tasks, expense events)

**Regulatory story:** Australian bank demonstrating APRA CPG 235 / BCBS 239 compliance: data lineage, classification, ownership, and quality checks across all sources, discoverable in one governed catalog.

---

## Prerequisites

- ServiceNow instance with Workflow Data Fabric (WDF) enabled
- MID Server installed and connected to the instance
- Snowflake account with `COMPUTE_WH` warehouse
- Neon PostgreSQL project
- Python 3.9+ with dependencies:
  ```
  pip install snowflake-connector-python psycopg2-binary
  ```

---

## Setup

1. Copy `.env.example` to `.env` and fill in all values
2. Source the env file: `export $(grep -v '^#' .env | xargs)`

---

## Run Order

| Script | What it does |
|--------|-------------|
| `snowflake_setup.py` | Creates `APRA_RISK_DW.RISK` schema: tables, views, seed data |
| `snowflake_catalog.py` | Adds Snowflake Horizon tags, column-level sensitivity, DMFs, object comments |
| `neon_setup.py` | Creates `vw_budget_variance_detail` and `vw_budget_anomalies` views in Neon |
| `sn_govern.py` | Creates SN domains, glossary terms, enriches Neon asset descriptions |
| `sn_snowflake_catalog_ingest.py` | Injects Snowflake assets into SN Data Catalog (use if SNOWSK8S compute is not provisioned) |

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
