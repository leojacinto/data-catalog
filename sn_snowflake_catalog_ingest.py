"""
Ingests Snowflake catalog metadata into ServiceNow Data Catalog.

Reads live from Snowflake's own catalog layer built by snowflake_catalog.py:
  - Object comments (INFORMATION_SCHEMA) -> SN asset descriptions
  - Table-level tags (TAG_REFERENCES_ALL_COLUMNS) -> SN short_description / additional_info
  - Column-level tags -> SN column records with tag annotations
  - DMF definitions (INFORMATION_SCHEMA.FUNCTIONS) -> noted in asset descriptions

Used because KOS SnowflakeCollector requires SNOWSK8S compute, which is not
provisioned on PDI instances. This script simulates what the collector would do.
"""
import urllib.request, json, base64, os, warnings
import snowflake.connector
warnings.filterwarnings('ignore')

# ── Snowflake connection ──────────────────────────────────────────────────────
sf = snowflake.connector.connect(
    account=os.environ['SF_ACCOUNT'],
    user=os.environ['SF_USER'],
    password=os.environ['SF_PASSWORD'],
    login_timeout=15
)
sfc = sf.cursor()
sfc.execute("USE DATABASE APRA_RISK_DW")
sfc.execute("USE SCHEMA RISK")
sfc.execute("USE WAREHOUSE COMPUTE_WH")

# ── ServiceNow connection ─────────────────────────────────────────────────────
BASE = f'https://{os.environ["SN_INSTANCE"]}.service-now.com'
AUTH = base64.b64encode(f'{os.environ["SN_USER"]}:{os.environ["SN_PASSWORD"]}'.encode()).decode()
H = {'Authorization': f'Basic {AUTH}', 'Content-Type': 'application/json', 'Accept': 'application/json'}
RISK_DOMAIN = os.environ.get('SN_RISK_DOMAIN_SYS_ID', '')

def sn_post(path, data):
    req = urllib.request.Request(f'{BASE}{path}', json.dumps(data).encode(), H, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def sn_get(path):
    req = urllib.request.Request(f'{BASE}{path}', headers=H)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

# ── Step 1: Pull object comments from Snowflake ───────────────────────────────
print('Reading object comments from Snowflake INFORMATION_SCHEMA...')
sfc.execute("""
    SELECT table_name, table_type, comment
    FROM INFORMATION_SCHEMA.TABLES
    WHERE table_schema = 'RISK'
    AND table_name IN ('TRADE','POSITION','BUDGET_PLAN','COUNTERPARTY',
                       'VW_PORTFOLIO_EXPOSURE','VW_TRADE_PNL_RECONCILIATION')
    ORDER BY table_type, table_name
""")
object_comments = {row[0]: {'type': row[1], 'comment': row[2] or ''} for row in sfc.fetchall()}
for name, meta in object_comments.items():
    print(f'  {meta["type"]:4s} {name}: {meta["comment"][:80]}')

# ── Step 2: Pull table-level tags from Snowflake ─────────────────────────────
print('\nReading table-level tags...')
table_tags = {}
for tbl in ['TRADE', 'POSITION', 'BUDGET_PLAN', 'COUNTERPARTY']:
    sfc.execute(f"""
        SELECT TAG_NAME, TAG_VALUE
        FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES(
            'APRA_RISK_DW.RISK.{tbl}', 'table'))
        ORDER BY TAG_NAME
    """)
    tags = {row[0]: row[1] for row in sfc.fetchall()}
    table_tags[tbl] = tags
    print(f'  {tbl}: {tags}')

# ── Step 3: Pull column-level tags ───────────────────────────────────────────
print('\nReading column-level tags...')
col_tags = {}
for tbl in ['TRADE', 'POSITION', 'BUDGET_PLAN', 'COUNTERPARTY']:
    sfc.execute(f"""
        SELECT COLUMN_NAME, TAG_NAME, TAG_VALUE
        FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS(
            'APRA_RISK_DW.RISK.{tbl}', 'table'))
        WHERE COLUMN_NAME IS NOT NULL
        ORDER BY COLUMN_NAME, TAG_NAME
    """)
    rows = sfc.fetchall()
    col_tags[tbl] = {}
    for col, tag_name, tag_val in rows:
        col_tags[tbl].setdefault(col, {})[tag_name] = tag_val
    print(f'  {tbl}: {len(rows)} column tag references')

# ── Step 4: Pull DMF definitions ─────────────────────────────────────────────
print('\nReading DMF definitions...')
sfc.execute("""
    SELECT FUNCTION_NAME, FUNCTION_DEFINITION, COMMENT
    FROM INFORMATION_SCHEMA.FUNCTIONS
    WHERE FUNCTION_SCHEMA = 'RISK'
    AND FUNCTION_NAME LIKE 'DMF_%'
""")
dmfs = sfc.fetchall()
dmf_summary = ', '.join(f'{r[0]}' for r in dmfs)
print(f'  DMFs: {dmf_summary}')
sf.close()

# ── Step 5: Build enriched descriptions from Snowflake catalog data ──────────
def build_description(obj_name, obj_type):
    base = object_comments.get(obj_name, {}).get('comment', '')
    tags = table_tags.get(obj_name, {})
    tag_parts = []
    if tags.get('DATA_DOMAIN'):
        tag_parts.append(f'Data Domain: {tags["DATA_DOMAIN"]}')
    if tags.get('SENSITIVITY'):
        tag_parts.append(f'Sensitivity: {tags["SENSITIVITY"]}')
    if tags.get('APRA_DATA_CLASS'):
        tag_parts.append(f'APRA Classification: {tags["APRA_DATA_CLASS"]}')
    if tags.get('DATA_OWNER'):
        tag_parts.append(f'Owner: {tags["DATA_OWNER"]}')
    if tags.get('BCBS239_CRITICAL') == 'YES':
        tag_parts.append('BCBS 239 Critical: YES')
    # Note attached DMFs if any
    attached_dmfs = [r[0] for r in dmfs if obj_name in r[2] or obj_name in r[1]]
    if attached_dmfs:
        tag_parts.append(f'Quality checks: {", ".join(attached_dmfs)}')
    suffix = ' | '.join(tag_parts)
    return f'{base}  [{suffix}]' if suffix else base

def build_col_description(tbl, col):
    tags = col_tags.get(tbl, {}).get(col, {})
    parts = [f'{k}: {v}' for k, v in tags.items()]
    return ' | '.join(parts) if parts else ''

# ── Step 6: Create DB and Schema records in SN ───────────────────────────────
print('\nCreating ServiceNow catalog records...')

db_r = sn_post('/api/now/table/sn_dcg_cc_kos_database', {
    'name': 'APRA_RISK_DW',
    'description': 'Snowflake data warehouse for APRA-regulated risk data. Contains trading, position, counterparty, and budget data for the Risk and Finance domains. Subject to BCBS 239 and APRA CPG 235 governance requirements.',
    'domain': RISK_DOMAIN,
    'active': 'true',
    'source': 'Snowflake',
    'metadata_collected_by': 'Snowflake APRA Risk DW',
})
db_id = db_r.get('result', {}).get('sys_id', '')
print(f'  DB APRA_RISK_DW: {db_id}')

schema_r = sn_post('/api/now/table/sn_dcg_cc_kos_database_schema', {
    'name': 'RISK',
    'description': 'Risk schema containing trading, position, counterparty, and budget data for APRA regulatory reporting.',
    'domain': RISK_DOMAIN,
    'active': 'true',
    'source': 'Snowflake',
})
schema_id = schema_r.get('result', {}).get('sys_id', '')
print(f'  Schema RISK: {schema_id}')

# ── Step 7: Create table records with Snowflake-sourced metadata ──────────────
print('\nCreating table assets...')
table_ids = {}
for tbl_name, meta in object_comments.items():
    if meta['type'] != 'BASE TABLE':
        continue
    desc = build_description(tbl_name, 'TABLE')
    r = sn_post('/api/now/table/sn_dcg_cc_kos_database_table', {
        'name': tbl_name,
        'description': desc,
        'domain': RISK_DOMAIN,
        'active': 'true',
        'source': 'Snowflake',
        'metadata_collected_by': 'Snowflake APRA Risk DW',
    })
    sid = r.get('result', {}).get('sys_id', '')
    table_ids[tbl_name] = sid
    print(f'  TABLE {tbl_name}: {sid or "ERR: " + str(r.get("error",""))[:80]}')

# ── Step 8: Create column records with column-level tag annotations ───────────
print('\nCreating column assets...')
for tbl_name, tbl_sid in table_ids.items():
    if not tbl_sid:
        continue
    cols = col_tags.get(tbl_name, {})
    for col_name, tags in cols.items():
        col_desc = build_col_description(tbl_name, col_name)
        r = sn_post('/api/now/table/sn_dcg_cc_kos_database_column', {
            'name': col_name,
            'description': col_desc,
            'parent': tbl_sid,
            'active': 'true',
            'source': 'Snowflake',
        })
        sid = r.get('result', {}).get('sys_id', '')
        print(f'  COL {tbl_name}.{col_name}: {sid or "ERR: " + str(r.get("error",""))[:60]}')

# ── Step 9: Create view records ───────────────────────────────────────────────
print('\nCreating view assets...')
view_ids = {}
for view_name, meta in object_comments.items():
    if meta['type'] != 'VIEW':
        continue
    desc = build_description(view_name, 'VIEW')
    r = sn_post('/api/now/table/sn_dcg_cc_kos_database_view', {
        'name': view_name,
        'description': desc,
        'domain': RISK_DOMAIN,
        'active': 'true',
        'source': 'Snowflake',
        'metadata_collected_by': 'Snowflake APRA Risk DW',
    })
    sid = r.get('result', {}).get('sys_id', '')
    view_ids[view_name] = sid
    print(f'  VIEW {view_name}: {sid or "ERR: " + str(r.get("error",""))[:80]}')

print('\nDone.')
print('Tables:', table_ids)
print('Views:', view_ids)
