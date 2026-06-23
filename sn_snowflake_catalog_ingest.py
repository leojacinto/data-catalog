"""
Manually injects Snowflake catalog assets into ServiceNow Data Catalog
via sn_dcg_cc_kos_database_table and related tables.
Used because SNOWSK8S compute is not authorized on this PDI instance
and MID is not supported by SnowflakeCollector.
"""
import urllib.request, json, base64, os

BASE = f'https://{os.environ["SN_INSTANCE"]}.service-now.com'
AUTH = base64.b64encode(f'{os.environ["SN_USER"]}:{os.environ["SN_PASSWORD"]}'.encode()).decode()
H = {'Authorization': f'Basic {AUTH}', 'Content-Type': 'application/json', 'Accept': 'application/json'}
RISK_DOMAIN = os.environ.get('SN_RISK_DOMAIN_SYS_ID', '')

def post(path, data):
    req = urllib.request.Request(f'{BASE}{path}', json.dumps(data).encode(), H, method='POST')
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def patch(path, data):
    req = urllib.request.Request(f'{BASE}{path}', json.dumps(data).encode(), H, method='PATCH')
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def get(path):
    req = urllib.request.Request(f'{BASE}{path}', headers=H)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

# First: find or create the Snowflake database and schema catalog entries
# Check if a Snowflake DB already exists
r = get('/api/now/table/sn_dcg_cc_kos_database?sysparm_query=nameLIKEAPRA&sysparm_fields=sys_id,name&sysparm_limit=3')
sf_dbs = r.get('result', [])
print('Existing SF DB entries:', sf_dbs)

# Create Database entry
db_r = post('/api/now/table/sn_dcg_cc_kos_database', {
    'name': 'APRA_RISK_DW',
    'description': 'Snowflake data warehouse for APRA-regulated risk data. Contains trading, position, counterparty, and budget data for the Risk and Finance domains. Subject to BCBS 239 and APRA CPG 235 governance requirements.',
    'domain': RISK_DOMAIN,
    'active': 'true',
    'source': 'Snowflake',
    'metadata_collected_by': 'Snowflake APRA Risk DW',
})
db_id = db_r.get('result', {}).get('sys_id', '')
print(f'DB APRA_RISK_DW: {db_id}')

# Create Schema entry
schema_r = post('/api/now/table/sn_dcg_cc_kos_database_schema', {
    'name': 'RISK',
    'description': 'Risk schema containing all trading, position, and counterparty data for APRA regulatory reporting.',
    'domain': RISK_DOMAIN,
    'active': 'true',
    'source': 'Snowflake',
})
schema_id = schema_r.get('result', {}).get('sys_id', '')
print(f'Schema RISK: {schema_id}')

# Define tables to create
tables = [
    {
        'name': 'TRADE',
        'description': 'Executed trade records sourced from MUREX trading system. Each row represents a single trade booking including counterparty, instrument, notional and settlement details. BCBS 239 critical data lineage asset. Sensitivity: CONFIDENTIAL. Data Domain: TRADING.',
        'tags': 'BCBS239_CRITICAL,TRADING,CONFIDENTIAL',
        'row_count': '5',
    },
    {
        'name': 'POSITION',
        'description': 'Daily end-of-day portfolio positions aggregated from MUREX. Includes P&L (daily, MTD, YTD) and 1-day VaR per instrument per book. APRA CPG 235 reportable risk data. Sensitivity: RESTRICTED. Data Domain: RISK.',
        'tags': 'BCBS239_CRITICAL,RISK,RESTRICTED',
        'row_count': '5',
    },
    {
        'name': 'BUDGET_PLAN',
        'description': 'Approved annual budget allocations by cost centre and GL account. Source of truth for budget vs actual variance analysis reconciled against Neon PostgreSQL operational data. Sensitivity: CONFIDENTIAL. Data Domain: FINANCE.',
        'tags': 'FINANCE,CONFIDENTIAL',
        'row_count': '5',
    },
    {
        'name': 'COUNTERPARTY',
        'description': 'Counterparty master reference including LEI codes for regulatory reporting. APRA-regulated flag indicates entities subject to prudential oversight. LEI column tagged REGULATORY. Sensitivity: CONFIDENTIAL. Data Domain: REFERENCE.',
        'tags': 'BCBS239_CRITICAL,REFERENCE,CONFIDENTIAL',
        'row_count': '5',
    },
]

views = [
    {
        'name': 'VW_PORTFOLIO_EXPOSURE',
        'description': 'Aggregated portfolio exposure by asset class and book from POSITION table. Used for daily risk reporting and APRA capital adequacy calculations. Column-level lineage: POSITION.',
        'tags': 'BCBS239_CRITICAL,RISK,RESTRICTED',
    },
    {
        'name': 'VW_TRADE_PNL_RECONCILIATION',
        'description': 'Trade-to-position P&L reconciliation. Identifies breaks between trade bookings and end-of-day position values. Feeds ServiceNow variance tasks for operations remediation. Column-level lineage: TRADE, VW_PORTFOLIO_EXPOSURE.',
        'tags': 'BCBS239_CRITICAL,RISK,RESTRICTED',
    },
]

print('\nCreating Snowflake table assets...')
table_ids = {}
for t in tables:
    r = post('/api/now/table/sn_dcg_cc_kos_database_table', {
        'name': t['name'],
        'description': t['description'],
        'domain': RISK_DOMAIN,
        'active': 'true',
        'source': 'Snowflake',
        'tags': t.get('tags', ''),
        'row_count': t.get('row_count', ''),
        'metadata_collected_by': 'Snowflake APRA Risk DW',
    })
    sid = r.get('result', {}).get('sys_id', '')
    table_ids[t['name']] = sid
    print(f'  TABLE {t["name"]}: {sid or "ERR: " + str(r.get("error",""))[:60]}')

print('\nCreating Snowflake view assets...')
view_ids = {}
for v in views:
    r = post('/api/now/table/sn_dcg_cc_kos_database_view', {
        'name': v['name'],
        'description': v['description'],
        'domain': RISK_DOMAIN,
        'active': 'true',
        'source': 'Snowflake',
        'tags': v.get('tags', ''),
        'metadata_collected_by': 'Snowflake APRA Risk DW',
    })
    sid = r.get('result', {}).get('sys_id', '')
    view_ids[v['name']] = sid
    print(f'  VIEW {v["name"]}: {sid or "ERR: " + str(r.get("error",""))[:60]}')

print('\nDone. Snowflake assets are now in the ServiceNow Data Catalog.')
print('Table IDs:', table_ids)
print('View IDs:', view_ids)
