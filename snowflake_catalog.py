"""
Builds Snowflake Horizon catalog layer on top of APRA_RISK_DW.RISK:
- Object tags (data domain, sensitivity, APRA classification)
- Column-level tag assignments
- Data Metric Functions (quality checks)
- Comments on all objects (these appear in SN catalog as descriptions)
"""
import snowflake.connector, os, warnings
warnings.filterwarnings('ignore')

conn = snowflake.connector.connect(
    account=os.environ['SF_ACCOUNT'],
    user=os.environ['SF_USER'],
    password=os.environ['SF_PASSWORD'],
    login_timeout=15
)
cur = conn.cursor()
cur.execute("USE DATABASE APRA_RISK_DW")
cur.execute("USE SCHEMA RISK")
cur.execute("USE WAREHOUSE COMPUTE_WH")

def run(sql, label=None):
    try:
        cur.execute(sql)
        lbl = label or sql.strip()[:60]
        print(f'OK: {lbl}')
    except Exception as e:
        lbl = label or sql.strip()[:60]
        print(f'ERR [{lbl}]: {str(e)[:120]}')

# ── 1. Create governance tags ────────────────────────────────────────────────
run("CREATE TAG IF NOT EXISTS DATA_DOMAIN ALLOWED_VALUES 'RISK','TRADING','FINANCE','REFERENCE','OPERATIONS'",
    "TAG: DATA_DOMAIN")

run("CREATE TAG IF NOT EXISTS SENSITIVITY ALLOWED_VALUES 'PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED'",
    "TAG: SENSITIVITY")

run("CREATE TAG IF NOT EXISTS APRA_DATA_CLASS ALLOWED_VALUES 'RISK_DATA','PII','FINANCIAL','REGULATORY','REFERENCE'",
    "TAG: APRA_DATA_CLASS")

run("CREATE TAG IF NOT EXISTS DATA_OWNER COMMENT='Business owner of this asset'",
    "TAG: DATA_OWNER")

run("CREATE TAG IF NOT EXISTS DATA_STEWARD COMMENT='Technical steward responsible for quality'",
    "TAG: DATA_STEWARD")

run("CREATE TAG IF NOT EXISTS BCBS239_CRITICAL ALLOWED_VALUES 'YES','NO' COMMENT='Critical risk data under BCBS 239 / APRA CPG 235'",
    "TAG: BCBS239_CRITICAL")

# ── 2. Tag tables ────────────────────────────────────────────────────────────
table_tags = {
    'TRADE': {
        'DATA_DOMAIN': 'TRADING',
        'SENSITIVITY': 'CONFIDENTIAL',
        'APRA_DATA_CLASS': 'RISK_DATA',
        'DATA_OWNER': 'Head of Trading Operations',
        'DATA_STEWARD': 'p.sharma@bank.com.au',
        'BCBS239_CRITICAL': 'YES',
    },
    'POSITION': {
        'DATA_DOMAIN': 'RISK',
        'SENSITIVITY': 'RESTRICTED',
        'APRA_DATA_CLASS': 'RISK_DATA',
        'DATA_OWNER': 'Chief Risk Officer',
        'DATA_STEWARD': 'e.thompson@bank.com.au',
        'BCBS239_CRITICAL': 'YES',
    },
    'BUDGET_PLAN': {
        'DATA_DOMAIN': 'FINANCE',
        'SENSITIVITY': 'CONFIDENTIAL',
        'APRA_DATA_CLASS': 'FINANCIAL',
        'DATA_OWNER': 'CFO Office',
        'DATA_STEWARD': 'e.thompson@bank.com.au',
        'BCBS239_CRITICAL': 'NO',
    },
    'COUNTERPARTY': {
        'DATA_DOMAIN': 'REFERENCE',
        'SENSITIVITY': 'CONFIDENTIAL',
        'APRA_DATA_CLASS': 'REGULATORY',
        'DATA_OWNER': 'Credit Risk Management',
        'DATA_STEWARD': 'm.sullivan@bank.com.au',
        'BCBS239_CRITICAL': 'YES',
    },
}

for tbl, tags in table_tags.items():
    for tag, val in tags.items():
        run(f"ALTER TABLE {tbl} SET TAG {tag} = '{val}'", f"TAG {tbl}.{tag}")

# Tag views too
for view in ['VW_PORTFOLIO_EXPOSURE', 'VW_TRADE_PNL_RECONCILIATION']:
    run(f"ALTER VIEW {view} SET TAG DATA_DOMAIN = 'RISK'", f"TAG {view}.DATA_DOMAIN")
    run(f"ALTER VIEW {view} SET TAG SENSITIVITY = 'RESTRICTED'", f"TAG {view}.SENSITIVITY")
    run(f"ALTER VIEW {view} SET TAG BCBS239_CRITICAL = 'YES'", f"TAG {view}.BCBS239")

# ── 3. Column-level tags (PII and regulatory) ────────────────────────────────
col_tags = [
    # TRADE - PII / regulatory
    ('TRADE', 'TRADER_NAME',     'SENSITIVITY', 'CONFIDENTIAL'),
    ('TRADE', 'TRADER_ID',       'APRA_DATA_CLASS', 'PII'),
    ('TRADE', 'COUNTERPARTY',    'APRA_DATA_CLASS', 'REGULATORY'),
    ('TRADE', 'NOTIONAL_AUD',    'SENSITIVITY', 'RESTRICTED'),
    ('TRADE', 'MARKET_VALUE_AUD','SENSITIVITY', 'RESTRICTED'),
    # POSITION - all restricted
    ('POSITION', 'NET_EXPOSURE',    'SENSITIVITY', 'RESTRICTED'),
    ('POSITION', 'VAR_1DAY',        'SENSITIVITY', 'RESTRICTED'),
    ('POSITION', 'PNL_DAILY',       'SENSITIVITY', 'RESTRICTED'),
    # COUNTERPARTY - LEI is regulatory identifier
    ('COUNTERPARTY', 'LEI_CODE',           'APRA_DATA_CLASS', 'REGULATORY'),
    ('COUNTERPARTY', 'INTERNAL_LIMIT_AUD', 'SENSITIVITY', 'RESTRICTED'),
    ('COUNTERPARTY', 'CREDIT_RATING',      'APRA_DATA_CLASS', 'RISK_DATA'),
    # BUDGET_PLAN - owner info is PII
    ('BUDGET_PLAN', 'OWNER_EMAIL',   'APRA_DATA_CLASS', 'PII'),
    ('BUDGET_PLAN', 'OWNER_NAME',    'APRA_DATA_CLASS', 'PII'),
]

for tbl, col, tag, val in col_tags:
    run(f"ALTER TABLE {tbl} MODIFY COLUMN {col} SET TAG {tag} = '{val}'",
        f"COL TAG {tbl}.{col}.{tag}")

# ── 4. Object comments (show as descriptions in SN catalog) ─────────────────
comments = [
    ("TABLE TRADE",    "Executed trade records sourced from MUREX trading system. Each row represents a single trade booking including counterparty, instrument, notional and settlement details. BCBS 239 critical data lineage asset."),
    ("TABLE POSITION", "Daily end-of-day portfolio positions aggregated from MUREX. Includes P&L (daily, MTD, YTD) and 1-day VaR per instrument per book. APRA CPG 235 reportable risk data."),
    ("TABLE BUDGET_PLAN", "Approved annual budget allocations by cost centre and GL account. Source of truth for budget vs actual variance analysis reconciled against Neon PostgreSQL operational data."),
    ("TABLE COUNTERPARTY", "Counterparty master reference including LEI codes for regulatory reporting. APRA-regulated flag indicates entities subject to prudential oversight."),
    ("VIEW VW_PORTFOLIO_EXPOSURE", "Aggregated portfolio exposure by asset class and book from POSITION table. Used for daily risk reporting and APRA capital adequacy calculations. Lineage: POSITION."),
    ("VIEW VW_TRADE_PNL_RECONCILIATION", "Trade-to-position P&L reconciliation. Identifies breaks between trade bookings and end-of-day position values. Feeds ServiceNow variance tasks for operations remediation. Lineage: TRADE, VW_PORTFOLIO_EXPOSURE."),
]

for obj, comment in comments:
    run(f"COMMENT ON {obj} IS $${comment}$$", f"COMMENT {obj[:30]}")

# ── 5. Data Metric Functions on critical columns ─────────────────────────────
run("""CREATE OR REPLACE DATA METRIC FUNCTION dmf_null_notional()
    RETURNS NUMBER
    COMMENT='Count of TRADE rows where notional is null or zero - data quality check for BCBS 239'
    AS $$
        SELECT COUNT(*) FROM APRA_RISK_DW.RISK.TRADE
        WHERE NOTIONAL_AUD IS NULL OR NOTIONAL_AUD = 0
    $$""", "DMF: null_notional")

run("""CREATE OR REPLACE DATA METRIC FUNCTION dmf_unsettled_trades_gt5d()
    RETURNS NUMBER
    COMMENT='Count of trades in PENDING status older than 5 days - settlement risk indicator'
    AS $$
        SELECT COUNT(*) FROM APRA_RISK_DW.RISK.TRADE
        WHERE STATUS = 'PENDING'
        AND DATEDIFF(day, SETTLEMENT_DATE, CURRENT_DATE()) > 5
    $$""", "DMF: unsettled_trades_gt5d")

run("""CREATE OR REPLACE DATA METRIC FUNCTION dmf_missing_lei()
    RETURNS NUMBER
    COMMENT='Counterparties missing LEI code - regulatory data completeness check'
    AS $$
        SELECT COUNT(*) FROM APRA_RISK_DW.RISK.COUNTERPARTY
        WHERE LEI_CODE IS NULL OR TRIM(LEI_CODE) = ''
    $$""", "DMF: missing_lei")

# ── 6. Verify catalog is populated ──────────────────────────────────────────
print('\n── Catalog verification ──')
cur.execute("SELECT TAG_NAME, TAG_VALUE, OBJECT_NAME, COLUMN_NAME FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS('APRA_RISK_DW.RISK.TRADE', 'table')) ORDER BY TAG_NAME, COLUMN_NAME NULLS FIRST")
rows = cur.fetchall()
print(f'TRADE tag references: {len(rows)}')
for r in rows[:6]: print(f'  {r[0]}={r[1]} on {r[2]}.{r[3] or "(table)"}')

cur.execute("SELECT * FROM INFORMATION_SCHEMA.OBJECT_PRIVILEGES WHERE OBJECT_SCHEMA='RISK' LIMIT 3")
print(f'\nSchema objects tagged and ready.')

cur.execute("SHOW TAGS IN SCHEMA APRA_RISK_DW.RISK")
tags = cur.fetchall()
print(f'Tags in schema: {[r[1] for r in tags]}')

conn.close()
print('\nSnowflake catalog layer complete.')
