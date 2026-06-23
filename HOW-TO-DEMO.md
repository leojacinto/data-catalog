# ServiceNow Workflow Data Fabric - Banking Demo Guide
## APRA CPG 235 / BCBS 239 Data Catalog Story

**Instance:** `<YOUR_SN_INSTANCE>.service-now.com`  
**Theme:** An Australian bank's Chief Data Officer needs to demonstrate to APRA that risk data is governed, lineage is traceable, and data quality is measurable - across all systems.

---

## The Story in One Sentence

> *"Our risk data lives in Snowflake. Our reconciliation data lives in Neon PostgreSQL. Our operational workflows run in ServiceNow. With Workflow Data Fabric, our CDO has one catalog to govern all of it, with lineage from trade execution to budget variance and data quality checks mapped to every critical field."*

---

## Architecture

```
SNOWFLAKE (APRA_RISK_DW.RISK)          NEON POSTGRESQL (neondb)
  ├── TRADE                    ──►        ├── monthly_variance_detail
  ├── POSITION                            ├── dim_cost_center
  ├── BUDGET_PLAN                         ├── dim_gl_account
  ├── COUNTERPARTY                        ├── dim_vendor
  ├── VW_PORTFOLIO_EXPOSURE               ├── VARIANCE_BASELINE_V
  └── VW_TRADE_PNL_RECONCILIATION         ├── vw_budget_variance_detail ◄ (lineage)
                                          └── vw_budget_anomalies       ◄ (lineage)
                   │                                    │
                   └──────────────┬─────────────────────┘
                                  ▼
                   SERVICENOW WORKFLOW DATA FABRIC
                   ├── Data Catalog (meta-catalog of both)
                   ├── ZCC Tables (live operational data)
                   │     ├── x_snc_forecast_v_0_df_mv_detail  (ML forecast)
                   │     ├── x_snc_forecast_v_0_variance_task (remediation tasks)
                   │     └── x_snc_forecast_v_0_expense_transaction_event
                   ├── Glossary Terms (BCBS 239, VaR, P&L Recon, LEI...)
                   ├── Domains (APRA Risk Management, Financial Operations)
                   └── Data Products (to build in demo)
```

---

## Demo Flow (15 minutes)

### Act 1 - The Problem (2 min)
**Talking point:** "A bank's risk data is scattered. Snowflake has trading data. A PostgreSQL warehouse has reconciliation data. ServiceNow has the operational workflows. The regulator wants to know: where does your P&L number come from? Who owns it? Is it quality-checked?"

Navigate to: **All → Workflow Data Fabric → Workflow Data Fabric Home**

Show the landing page. Point out Connect Hub, Data Catalog, Data Workbench.

---

### Act 2 - Connect Hub: Two Sources, One Platform (3 min)

Navigate to: **Connect Hub** (left sidebar)

Show two active collectors:
1. **Neon** - PostgreSQL reconciliation database (middle-office)
2. **Snowflake APRA Risk DW** - front-office risk data warehouse

**Talking point:** *"We connected both systems once. The metadata collector runs automatically and keeps the catalog current with no manual documentation or spreadsheets."*

Click the Neon collector → show **Run History** → last run: COMPLETED, 175 assets discovered.

---

### Act 3 - Data Catalog: Discover & Govern (5 min)

Navigate to: **Data Catalog** (left sidebar in WDF Home)

#### 3a. Browse by Domain
Filter by domain: **Financial Operations**  
Show: `monthly_variance_detail`, `dim_cost_center`, `dim_gl_account`, `vw_budget_variance_detail`, `vw_budget_anomalies`

**Talking point:** *"Everything in the Financial Operations domain is tagged, described, and owned. A new analyst can find this in seconds instead of asking around."*

#### 3b. Asset Detail - vw_budget_variance_detail
Click `vw_budget_variance_detail`

- **Overview tab:** Show the description. Point out Source = Neon PostgreSQL.
- **Columns tab:** Show all 24 columns - `cost_center_owner`, `account_name`, `vendor_category` pulled from different dim tables.
- **Lineage tab:** Show column-level lineage. `cost_center_owner` traces back to `dim_cost_center.owner_name`, `account_name` traces to `dim_gl_account.account_name`.  
  **Talking point:** *"This is column-level lineage. APRA CPG 235 doesn't just want table lineage - they want to know which source field each value came from. This is that."*

#### 3c. Glossary Terms
Navigate to: **All → Workflow Data Fabric → Business Glossary**  
Show: BCBS 239, Value at Risk, P&L Reconciliation, LEI Code, Net Exposure

**Talking point:** *"The glossary bridges the gap between what a regulator calls it (BCBS 239, LEI) and what the data engineer named it (lei_code, var_1day). Link a glossary term to an asset and every consumer immediately understands the regulatory context."*

#### 3d. Trust Score
Back in the catalog, point out the Trust Score on any asset.  
**Talking point:** *"Trust Score surfaces governance completeness: does this asset have a description? An owner? A domain? A glossary term? The CDO can see at a glance which assets are governance-ready for the regulator."*

---

### Act 4 - Snowflake Catalog: Sensitivity Tags (2 min)

Navigate to Catalog, search for **TRADE** or **POSITION** (visible after Snowflake collector run)

Click `TRADE` asset:
- Show `SENSITIVITY = RESTRICTED` tag on `NOTIONAL_AUD`, `MARKET_VALUE_AUD`
- Show `APRA_DATA_CLASS = REGULATORY` on `COUNTERPARTY`, `LEI_CODE`
- Show `BCBS239_CRITICAL = YES` on the table

**Talking point:** *"These tags came directly from Snowflake Horizon, Snowflake's own governance layer. ServiceNow didn't duplicate them; it ingested them. This is the catalog of catalogs: Snowflake governs its own data, and we surface that governance metadata here alongside the PostgreSQL assets."*

---

### Act 5 - ZCC: Live Operational Data (1 min)

Navigate to: **All → x_snc_forecast_v_0_df_mv_detail_list.do**  
(or via: `https://<YOUR_SN_INSTANCE>.service-now.com/x_snc_forecast_v_0_df_mv_detail_list.do`)

Show the live forecast variance data: `forecast_source`, `variance_pct`, `anomaly_flag`.

**Talking point:** *"Zero Copy Connector. This data isn't copied into ServiceNow - it's queried live from the source. The data stays in place, governance travels with it."*

---

### Act 6 - Data Product: Packaging for Consumers (2 min)

Navigate to: **All → Workflow Data Fabric → Data Workbench**

**Talking point:** *"A data steward takes the governed assets from the catalog and packages them into a Data Product: a governed, versioned, access-controlled contract that any team can consume."*

Show (or create) a Data Product named **"APRA Financial Risk Intelligence"**:
- Add Data Interface from `vw_budget_variance_detail` (Neon)
- Add Data Interface from `vw_budget_anomalies` (Neon)
- Publish → appears in Data Catalog
- Consumers can request access directly from the catalog

---

## Key URLs

| Resource | URL |
|----------|-----|
| WDF Home | `https://<YOUR_SN_INSTANCE>.service-now.com/now/wdf/home` |
| Connect Hub | `https://<YOUR_SN_INSTANCE>.service-now.com/now/wdf/connect-hub` |
| Data Catalog | `https://<YOUR_SN_INSTANCE>.service-now.com/now/wdf/data-catalog` |
| Data Workbench | `https://<YOUR_SN_INSTANCE>.service-now.com/now/wdf/data-workbench` |
| ZCC Live Data | `https://<YOUR_SN_INSTANCE>.service-now.com/x_snc_forecast_v_0_df_mv_detail_list.do` |
| Neon Collector Run | `https://<YOUR_SN_INSTANCE>.service-now.com/now/wdf/connect-hub` |
| Glossary Terms | `https://<YOUR_SN_INSTANCE>.service-now.com/now/nav/ui/classic/params/target/sn_dcg_core_glossary_term_list.do` |
| Domains | `https://<YOUR_SN_INSTANCE>.service-now.com/now/nav/ui/classic/params/target/sn_dcg_core_domain_list.do` |

---

## Regulatory Talking Points

| Claim | Evidence in Demo |
|-------|-----------------|
| BCBS 239 / APRA CPG 235: Data lineage | Column-level lineage on `vw_budget_variance_detail` → source tables |
| BCBS 239: Data accuracy | Data Metric Functions on Snowflake TRADE (dmf_null_notional) |
| CPG 235: Data classification | Sensitivity tags (RESTRICTED, CONFIDENTIAL) on Snowflake columns |
| CPG 235: Ownership | `DATA_OWNER`, `DATA_STEWARD` tags + catalog domain assignments |
| CPG 235: Discoverability | Business Glossary linking BCBS 239, VaR, LEI to technical assets |
| APRA reporting: LEI completeness | dmf_missing_lei DMF on COUNTERPARTY table |

---

## What Still Needs the UI (one-time setup)

1. **Snowflake collector** - The KOS SnowflakeCollector requires SNOWSK8S (ServiceNow hosted compute) which is not provisioned on this PDI. Snowflake assets (TRADE, POSITION, BUDGET_PLAN, COUNTERPARTY, VW_PORTFOLIO_EXPOSURE, VW_TRADE_PNL_RECONCILIATION) have been manually ingested into the catalog with full descriptions, tags, and domain assignments. In a production instance with SNOWSK8S provisioned, the collector would run automatically and also capture column-level lineage within Snowflake views.
2. **Create Data Interfaces + Data Product** - Go to Data Workbench, Create, follow wizard  
   *(Requires UI; no public REST API for Data Interface creation)*
3. **Link Glossary Terms to Assets** - In each asset detail page, add glossary term  
   *(Can be done via API once term and asset sys_ids are known)*

---

## Data Summary

| Source | Objects | Key Assets |
|--------|---------|-----------|
| Snowflake APRA_RISK_DW.RISK | 4 tables, 2 views, 6 tags, 2 DMFs | TRADE, POSITION, VW_TRADE_PNL_RECONCILIATION |
| Neon PostgreSQL neondb | 7 tables, 2 views | monthly_variance_detail, vw_budget_variance_detail |
| ServiceNow ZCC | 3 tables | df_mv_detail, variance_task, expense_transaction_event |
| **Total governed assets** | **~175 catalog records** | Across 2 domains, 8 glossary terms |
