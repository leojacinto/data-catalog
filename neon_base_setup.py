"""
Creates and seeds the base Neon PostgreSQL tables used by this demo.
These tables existed before the views (neon_setup.py) were created.
Run this first if starting from a blank Neon project.

Tables created:
  - dim_date
  - dim_cost_center
  - dim_gl_account
  - dim_vendor
  - monthly_variance_detail  (fact table, mapped via ZCC)
  - summary_variance          (mapped via ZCC)
  - VARIANCE_BASELINE_V       (view, baseline for anomaly detection)
"""
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
    # ── Dimension tables ─────────────────────────────────────────────────────

    """CREATE TABLE IF NOT EXISTS dim_date (
        date_key        DATE        PRIMARY KEY,
        fiscal_year     INTEGER     NOT NULL,
        fiscal_month    INTEGER     NOT NULL,
        fiscal_quarter  INTEGER     NOT NULL,
        period_label    VARCHAR(20),
        is_month_end    BOOLEAN     DEFAULT false
    )""",

    """CREATE TABLE IF NOT EXISTS dim_cost_center (
        cost_center     VARCHAR(20) PRIMARY KEY,
        department      VARCHAR(100),
        division        VARCHAR(100),
        owner_name      VARCHAR(100),
        owner_email     VARCHAR(100),
        active          BOOLEAN     DEFAULT true
    )""",

    """CREATE TABLE IF NOT EXISTS dim_gl_account (
        gl_account      INTEGER     PRIMARY KEY,
        account_name    VARCHAR(100),
        account_type    VARCHAR(50),
        parent_account  INTEGER,
        cost_category   VARCHAR(50)
    )""",

    """CREATE TABLE IF NOT EXISTS dim_vendor (
        vendor_name     VARCHAR(100) PRIMARY KEY,
        vendor_category VARCHAR(50),
        preferred       BOOLEAN     DEFAULT false,
        contract_end    DATE
    )""",

    # ── Fact table ───────────────────────────────────────────────────────────

    """CREATE TABLE IF NOT EXISTS monthly_variance_detail (
        id                  SERIAL      PRIMARY KEY,
        period              DATE        NOT NULL,
        fiscal_year         INTEGER,
        fiscal_month        INTEGER,
        cost_center         VARCHAR(20),
        gl_account          INTEGER,
        vendor              VARCHAR(100),
        budget_amount       NUMERIC(18,2),
        actual_amount       NUMERIC(18,2),
        variance_amount     NUMERIC(18,2) GENERATED ALWAYS AS (actual_amount - budget_amount) STORED,
        variance_pct        NUMERIC(8,4),
        forecast_source     VARCHAR(50),
        anomaly_flag        BOOLEAN     DEFAULT false,
        anomaly_reason      VARCHAR(200),
        service_category    VARCHAR(50),
        created_at          TIMESTAMPTZ DEFAULT now()
    )""",

    # ── Summary table ─────────────────────────────────────────────────────────

    """CREATE TABLE IF NOT EXISTS summary_variance (
        period          DATE        NOT NULL,
        cost_center     VARCHAR(20) NOT NULL,
        total_budget    NUMERIC(18,2),
        total_actual    NUMERIC(18,2),
        total_variance  NUMERIC(18,2),
        anomaly_count   INTEGER     DEFAULT 0,
        PRIMARY KEY (period, cost_center)
    )""",

    # ── Baseline view ─────────────────────────────────────────────────────────

    """CREATE OR REPLACE VIEW "VARIANCE_BASELINE_V" AS
    SELECT
        cost_center,
        gl_account,
        AVG(variance_pct)   AS avg_variance_pct,
        STDDEV(variance_pct) AS stddev_variance_pct,
        MIN(period)         AS baseline_from,
        MAX(period)         AS baseline_to
    FROM monthly_variance_detail
    WHERE fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE) - 1
    GROUP BY cost_center, gl_account""",
]

# ── Seed dimension data ───────────────────────────────────────────────────────

seed_statements = [
    """INSERT INTO dim_date (date_key, fiscal_year, fiscal_month, fiscal_quarter, period_label, is_month_end)
    VALUES
        ('2025-01-31', 2025, 1, 1, 'FY25 Jan', true),
        ('2025-02-28', 2025, 2, 1, 'FY25 Feb', true),
        ('2025-03-31', 2025, 3, 1, 'FY25 Mar', true),
        ('2025-04-30', 2025, 4, 2, 'FY25 Apr', true),
        ('2025-05-31', 2025, 5, 2, 'FY25 May', true),
        ('2025-06-30', 2025, 6, 2, 'FY25 Jun', true)
    ON CONFLICT DO NOTHING""",

    """INSERT INTO dim_cost_center (cost_center, department, division, owner_name, owner_email)
    VALUES
        ('CC-1001', 'Market Risk',        'Risk Management',    'Sarah Chen',      'sarah.chen@bank.com.au'),
        ('CC-1002', 'Credit Risk',        'Risk Management',    'James Liu',       'james.liu@bank.com.au'),
        ('CC-2001', 'Finance Operations', 'CFO',                'Anna Kowalski',   'anna.kowalski@bank.com.au'),
        ('CC-2002', 'Treasury',           'CFO',                'Michael Torres',  'michael.torres@bank.com.au'),
        ('CC-3001', 'Technology',         'COO',                'Priya Nair',      'priya.nair@bank.com.au')
    ON CONFLICT DO NOTHING""",

    """INSERT INTO dim_gl_account (gl_account, account_name, account_type, cost_category)
    VALUES
        (6001, 'Software Licensing',    'Opex', 'Technology'),
        (6002, 'Cloud Infrastructure',  'Opex', 'Technology'),
        (6003, 'Professional Services', 'Opex', 'External Labour'),
        (6004, 'Staff Salaries',        'Opex', 'People'),
        (6005, 'Data Services',         'Opex', 'Technology'),
        (7001, 'Capital Equipment',     'Capex', 'Technology')
    ON CONFLICT DO NOTHING""",

    """INSERT INTO dim_vendor (vendor_name, vendor_category, preferred, contract_end)
    VALUES
        ('Bloomberg LP',        'Data',        true,  '2026-12-31'),
        ('AWS',                 'Cloud',       true,  '2027-06-30'),
        ('Refinitiv',           'Data',        true,  '2026-09-30'),
        ('Accenture',           'Consulting',  false, '2025-12-31'),
        ('MSCI',                'Data',        true,  '2027-03-31'),
        ('Snowflake Inc',       'Cloud',       true,  '2027-12-31')
    ON CONFLICT DO NOTHING""",

    """INSERT INTO monthly_variance_detail
        (period, fiscal_year, fiscal_month, cost_center, gl_account, vendor,
         budget_amount, actual_amount, variance_pct, forecast_source, anomaly_flag, anomaly_reason, service_category)
    VALUES
        ('2025-01-31', 2025, 1, 'CC-1001', 6005, 'Bloomberg LP',   45000, 45000,  0.000,  'ACTUALS', false, null, 'Market Data'),
        ('2025-01-31', 2025, 1, 'CC-2001', 6001, 'Snowflake Inc',  30000, 31500,  0.050,  'ACTUALS', false, null, 'Technology'),
        ('2025-02-28', 2025, 2, 'CC-1001', 6005, 'Bloomberg LP',   45000, 45000,  0.000,  'ACTUALS', false, null, 'Market Data'),
        ('2025-02-28', 2025, 2, 'CC-3001', 6002, 'AWS',            80000, 94000,  0.175,  'ACTUALS', true,  'Cloud spend 17.5% over budget - spike in data egress', 'Technology'),
        ('2025-03-31', 2025, 3, 'CC-2002', 6003, 'Accenture',     120000, 138000, 0.150,  'ACTUALS', true,  'Consulting overage: scope creep on regulatory project', 'External Labour'),
        ('2025-04-30', 2025, 4, 'CC-1002', 6005, 'Refinitiv',      22000, 22000,  0.000,  'ML_MODEL', false, null, 'Market Data'),
        ('2025-05-31', 2025, 5, 'CC-3001', 6001, 'Snowflake Inc',  30000, 29100, -0.030,  'ML_MODEL', false, null, 'Technology'),
        ('2025-06-30', 2025, 6, 'CC-2001', 6004, null,            200000, 205000, 0.025,  'ACTUALS', false, null, 'People')
    ON CONFLICT DO NOTHING""",

    """INSERT INTO summary_variance (period, cost_center, total_budget, total_actual, total_variance, anomaly_count)
    VALUES
        ('2025-01-31', 'CC-1001', 45000,  45000,   0,     0),
        ('2025-01-31', 'CC-2001', 30000,  31500,   1500,  0),
        ('2025-02-28', 'CC-1001', 45000,  45000,   0,     0),
        ('2025-02-28', 'CC-3001', 80000,  94000,   14000, 1),
        ('2025-03-31', 'CC-2002', 120000, 138000,  18000, 1),
        ('2025-04-30', 'CC-1002', 22000,  22000,   0,     0),
        ('2025-05-31', 'CC-3001', 30000,  29100,  -900,   0),
        ('2025-06-30', 'CC-2001', 200000, 205000,  5000,  0)
    ON CONFLICT DO NOTHING""",
]

print('Creating base tables and views...')
for sql in statements:
    label = sql.strip().split('\n')[0][:60]
    try:
        cur.execute(sql)
        print(f'  OK: {label}')
    except Exception as e:
        print(f'  ERR: {label} => {e}')

print('\nSeeding data...')
for sql in seed_statements:
    label = sql.strip().split('\n')[0][:60]
    try:
        cur.execute(sql)
        print(f'  OK: {label}')
    except Exception as e:
        print(f'  ERR: {label} => {e}')

cur.close()
conn.close()
print('\nDone. Run neon_setup.py next to create the lineage views.')
