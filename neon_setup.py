import psycopg2, os

conn = psycopg2.connect(
    host=os.environ['NEON_HOST'],
    port=int(os.environ.get('NEON_PORT', '5432')),
    dbname=os.environ['NEON_DB'],
    user=os.environ['NEON_USER'],
    password=os.environ['NEON_PASSWORD'],
    sslmode='require',
    connect_timeout=15
)
conn.autocommit = True
cur = conn.cursor()

statements = [
    # View 1: Full variance enriched with dim lookups - column-level lineage across 4 tables
    """CREATE OR REPLACE VIEW vw_budget_variance_detail AS
    SELECT
        m.period,
        m.fiscal_year,
        m.fiscal_month,
        m.cost_center,
        cc.department,
        cc.division,
        cc.owner_name        AS cost_center_owner,
        cc.owner_email       AS cost_center_owner_email,
        m.gl_account,
        ga.account_name,
        ga.account_group,
        ga.expense_category,
        m.vendor,
        v.vendor_code,
        v.category           AS vendor_category,
        v.region             AS vendor_region,
        m.budget_amount_usd,
        m.actual_amount_usd,
        m.variance,
        m.variance_pct,
        m.forecast_source,
        m.anomaly_flag,
        m.anomaly_reason,
        m.service_category
    FROM monthly_variance_detail m
    LEFT JOIN dim_cost_center cc ON m.cost_center = cc.cost_center
    LEFT JOIN dim_gl_account  ga ON m.gl_account  = ga.gl_account
    LEFT JOIN dim_vendor       v  ON m.vendor      = v.vendor_name""",

    # View 2: Budget anomalies - actionable, clean lineage
    """CREATE OR REPLACE VIEW vw_budget_anomalies AS
    SELECT
        m.period,
        m.fiscal_year,
        m.cost_center,
        cc.department,
        cc.owner_name        AS cost_center_owner,
        cc.owner_email       AS cost_center_owner_email,
        m.gl_account,
        ga.account_name,
        m.vendor,
        m.actual_amount_usd,
        m.budget_amount_usd,
        m.variance,
        m.variance_pct,
        m.anomaly_reason,
        m.forecast_source
    FROM monthly_variance_detail m
    LEFT JOIN dim_cost_center cc ON m.cost_center = cc.cost_center
    LEFT JOIN dim_gl_account  ga ON m.gl_account  = ga.gl_account
    WHERE m.anomaly_flag = true""",
]

for sql in statements:
    label = sql.strip().split('\n')[0][:70]
    try:
        cur.execute(sql)
        print(f'OK: {label}')
    except Exception as e:
        print(f'ERR: {label}\n     {e}')

# Verify
cur.execute("SELECT table_name, table_type FROM information_schema.tables WHERE table_schema='public' ORDER BY table_type, table_name")
print('\nAll objects in Neon public schema:')
for row in cur.fetchall():
    print(f'  {row[1]}: {row[0]}')

conn.close()
print('\nDone.')
