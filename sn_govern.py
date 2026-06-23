"""
Governs the Data Catalog assets in ServiceNow:
- Creates domains (APRA Risk Management, Financial Operations)
- Creates glossary terms (BCBS 239, VaR, P&L Reconciliation, etc.)
- Enriches data asset descriptions for all Neon tables/views
"""
import urllib.request, json, urllib.parse, base64, os

BASE = f'https://{os.environ["SN_INSTANCE"]}.service-now.com'
AUTH = base64.b64encode(f'{os.environ["SN_USER"]}:{os.environ["SN_PASSWORD"]}'.encode()).decode()
HEADERS = {'Authorization': f'Basic {AUTH}', 'Content-Type': 'application/json', 'Accept': 'application/json'}

def sn_post(path, data):
    req = urllib.request.Request(f'{BASE}{path}', json.dumps(data).encode(), HEADERS, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'error': str(e)}

def sn_patch(path, data):
    req = urllib.request.Request(f'{BASE}{path}', json.dumps(data).encode(), HEADERS, method='PATCH')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'error': str(e)}

def sn_get(path):
    req = urllib.request.Request(f'{BASE}{path}', headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'error': str(e)}

# ── 1. Create Domains ────────────────────────────────────────────────────────
print('Creating domains...')

d1 = sn_post('/api/now/table/sn_dcg_core_domain', {
    'name': 'APRA Risk Management',
    'description': 'Risk data assets subject to APRA CPG 235 and BCBS 239 regulatory requirements. Covers trading positions, P&L, VaR, and counterparty exposure data sourced from the Snowflake risk data warehouse.'
})
risk_domain = d1.get('result', {}).get('sys_id', '')
print(f'Risk domain: {risk_domain}')

d2 = sn_post('/api/now/table/sn_dcg_core_domain', {
    'name': 'Financial Operations',
    'description': 'Operational finance data assets including budget variance, cost centre tracking, GL account actuals, and vendor spend. Sourced from Neon PostgreSQL reconciliation database and ServiceNow operational tables.'
})
fin_domain = d2.get('result', {}).get('sys_id', '')
print(f'Finance domain: {fin_domain}')

# ── 2. Create Glossary Terms ─────────────────────────────────────────────────
print('\nCreating glossary terms...')

terms = [
    {
        'name': 'BCBS 239',
        'definition': 'Basel Committee on Banking Supervision Principle 239. Requires banks to have strong risk data aggregation capabilities and risk reporting practices. In Australia, enforced by APRA under CPG 235 Data Risk Management.',
        'abbreviation': 'BCBS 239',
    },
    {
        'name': 'Value at Risk',
        'definition': 'A statistical measure of the potential loss in value of a portfolio over a defined period for a given confidence interval. The 1-day VaR at 99% confidence is an APRA-reportable capital adequacy metric.',
        'abbreviation': 'VaR',
    },
    {
        'name': 'P&L Reconciliation',
        'definition': 'The process of matching trade-level profit and loss bookings against end-of-day portfolio position values. Breaks (discrepancies) trigger operational tasks in ServiceNow for resolution by the Operations team.',
        'abbreviation': 'P&L Recon',
    },
    {
        'name': 'GL Account',
        'definition': 'General Ledger account code used to classify financial transactions by type (e.g., 610000 = Fixed Income Trading Revenue). Maps between the front-office trading system and the finance reconciliation database.',
        'abbreviation': 'GL',
    },
    {
        'name': 'Cost Centre',
        'definition': 'An organisational unit that incurs costs and is tracked for budget vs actual performance. Each cost centre maps to a business line (e.g., CC_RISK_001 = Risk Management - Fixed Income). Used in both Snowflake and Neon data assets.',
        'abbreviation': 'CC',
    },
    {
        'name': 'Budget Variance',
        'definition': 'The difference between approved budget and actual spend for a cost centre and GL account in a given period. A negative variance indicates overspend. Anomaly-flagged variances trigger automated review workflows in ServiceNow.',
        'abbreviation': '',
    },
    {
        'name': 'LEI Code',
        'definition': 'Legal Entity Identifier: a 20-character alphanumeric code that uniquely identifies legal entities participating in financial transactions. Mandatory for APRA regulatory reporting under the Financial Sector (Collection of Data) Act.',
        'abbreviation': 'LEI',
    },
    {
        'name': 'Net Exposure',
        'definition': 'The net market risk position of a portfolio after offsetting long and short positions in the same instrument. A key APRA capital adequacy input and BCBS 239 critical data element.',
        'abbreviation': '',
    },
]

term_ids = {}
for t in terms:
    body = {'name': t['name'], 'definition': t['definition']}
    if t.get('abbreviation'):
        body['abbreviation'] = t['abbreviation']
    r = sn_post('/api/now/table/sn_dcg_core_glossary_term', body)
    tid = r.get('result', {}).get('sys_id', '')
    term_ids[t['name']] = tid
    print(f'  Term "{t["name"]}": {tid or "ERR: " + str(r.get("error","?"))[:50]}')

# ── 3. Enrich Neon table/view asset descriptions ─────────────────────────────
print('\nEnriching asset descriptions...')

asset_descriptions = {
    'monthly_variance_detail': {
        'description': 'Monthly budget vs actual variance detail by cost centre, GL account, and vendor. Source table for all financial reconciliation and anomaly detection in the Financial Operations domain. Contains ML-flagged anomalies from the forecast model.',
        'domain': fin_domain,
    },
    'dim_cost_center': {
        'description': 'Cost centre dimension table mapping internal cost centre codes to business lines, departments, divisions, and responsible owners. Reference data shared across Snowflake (BUDGET_PLAN) and Neon (monthly_variance_detail).',
        'domain': fin_domain,
    },
    'dim_gl_account': {
        'description': 'General Ledger account dimension table. Maps GL account codes to account names, expense categories, and account groups. Links front-office trading GL codes (Snowflake TRADE/POSITION) to back-office reconciliation (Neon).',
        'domain': fin_domain,
    },
    'dim_vendor': {
        'description': 'Vendor master dimension table. Contains vendor codes, categories, regions, and countries for spend classification. Used in variance analysis to identify vendor-level budget overruns.',
        'domain': fin_domain,
    },
    'dim_date': {
        'description': 'Date dimension table providing fiscal calendar attributes including fiscal year, month, quarter labels, and month names. Supports time-series analysis across the financial operations dataset.',
        'domain': fin_domain,
    },
    'summary_variance': {
        'description': 'Summarised budget variance by cost centre and GL account at fiscal year level. Baseline comparison table used by the VARIANCE_BASELINE_V table and forecast models to measure performance against approved budgets.',
        'domain': fin_domain,
    },
    'VARIANCE_BASELINE_V': {
        'description': 'Baseline variance reference table storing period-level actual vs baseline comparisons. Acts as the source of truth for year-to-date variance tracking. Feeds the ML forecast model for anomaly detection.',
        'domain': fin_domain,
    },
    'vw_budget_variance_detail': {
        'description': 'Enriched budget variance view joining monthly_variance_detail with all dimension tables (dim_cost_center, dim_gl_account, dim_vendor). Provides full business context for each variance line including owner details, account names, and vendor categories. Primary view for Finance Operations reporting. Column-level lineage traces each field to its source table.',
        'domain': fin_domain,
    },
    'vw_budget_anomalies': {
        'description': 'Filtered view surfacing only ML-flagged anomalous budget variance lines. Joins with dim_cost_center and dim_gl_account for owner and account context. Direct input to ServiceNow Variance Task creation workflow. Column-level lineage: monthly_variance_detail, dim_cost_center, dim_gl_account.',
        'domain': fin_domain,
    },
}

# Find each asset and update it
for asset_name, attrs in asset_descriptions.items():
    r = sn_get(f'/api/now/table/sn_dcg_cc_kos_database_table?sysparm_query=name={urllib.parse.quote(asset_name)}&sysparm_fields=sys_id,name&sysparm_limit=1')
    rows = r.get('result', [])
    if not rows:
        r2 = sn_get(f'/api/now/table/sn_dcg_cc_kos_database_view?sysparm_query=name={urllib.parse.quote(asset_name)}&sysparm_fields=sys_id,name&sysparm_limit=1')
        rows = r2.get('result', [])
    if rows:
        sys_id = rows[0]['sys_id']
        tbl = 'sn_dcg_cc_kos_database_table' if 'table' in r.get('result', [{'x':1}])[0].get('sys_class_name','table') else 'sn_dcg_cc_kos_database_view'
        patch_data = {'description': attrs['description']}
        if attrs.get('domain'):
            patch_data['domain'] = attrs['domain']
        pr = sn_patch(f'/api/now/table/sn_dcg_core_resource/{sys_id}', patch_data)
        if pr.get('result'):
            print(f'  Updated {asset_name}: OK')
        else:
            # try direct table
            pr2 = sn_patch(f'/api/now/table/sn_dcg_cc_kos_database_table/{sys_id}', patch_data)
            if pr2.get('result'):
                print(f'  Updated {asset_name} (table): OK')
            else:
                pr3 = sn_patch(f'/api/now/table/sn_dcg_cc_kos_database_view/{sys_id}', patch_data)
                if pr3.get('result'):
                    print(f'  Updated {asset_name} (view): OK')
                else:
                    print(f'  {asset_name}: ERR {str(pr.get("error",pr))[:80]}')
    else:
        print(f'  {asset_name}: NOT FOUND in catalog')

print('\nDone.')
