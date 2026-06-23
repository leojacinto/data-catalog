import snowflake.connector, os, warnings
warnings.filterwarnings('ignore')

conn = snowflake.connector.connect(
    account=os.environ['SF_ACCOUNT'],
    user=os.environ['SF_USER'],
    password=os.environ['SF_PASSWORD'],
    login_timeout=15
)
cur = conn.cursor()

statements = [
    # Database and schema
    "CREATE DATABASE IF NOT EXISTS APRA_RISK_DW",
    "USE DATABASE APRA_RISK_DW",
    "CREATE SCHEMA IF NOT EXISTS RISK",
    "USE SCHEMA RISK",

    # Table 1: Individual trade records - source of truth
    """CREATE OR REPLACE TABLE TRADE (
        trade_id        VARCHAR(20)    NOT NULL PRIMARY KEY,
        trade_date      DATE           NOT NULL,
        settlement_date DATE,
        cost_center     VARCHAR(20),
        gl_account      INTEGER,
        asset_class     VARCHAR(50),
        instrument_id   VARCHAR(20),
        instrument_name VARCHAR(200),
        counterparty_id VARCHAR(20),
        counterparty    VARCHAR(100),
        direction       VARCHAR(4),
        notional_aud    NUMBER(18,2),
        market_value_aud NUMBER(18,2),
        currency        VARCHAR(3),
        trader_id       VARCHAR(20),
        trader_name     VARCHAR(100),
        book            VARCHAR(50),
        status          VARCHAR(20),
        source_system   VARCHAR(50)
    )""",

    # Table 2: Daily portfolio positions per book
    """CREATE OR REPLACE TABLE POSITION (
        position_id     VARCHAR(30)    NOT NULL PRIMARY KEY,
        position_date   DATE           NOT NULL,
        cost_center     VARCHAR(20),
        gl_account      INTEGER,
        book            VARCHAR(50),
        asset_class     VARCHAR(50),
        instrument_id   VARCHAR(20),
        instrument_name VARCHAR(200),
        long_notional   NUMBER(18,2),
        short_notional  NUMBER(18,2),
        net_exposure    NUMBER(18,2),
        market_value_aud NUMBER(18,2),
        pnl_daily       NUMBER(18,2),
        pnl_mtd         NUMBER(18,2),
        pnl_ytd         NUMBER(18,2),
        var_1day        NUMBER(18,2),
        currency        VARCHAR(3),
        source_system   VARCHAR(50)
    )""",

    # Table 3: Budget approved per cost centre / GL
    """CREATE OR REPLACE TABLE BUDGET_PLAN (
        budget_id       VARCHAR(20)    NOT NULL PRIMARY KEY,
        fiscal_year     INTEGER        NOT NULL,
        fiscal_month    INTEGER,
        cost_center     VARCHAR(20),
        gl_account      INTEGER,
        asset_class     VARCHAR(50),
        approved_budget_aud NUMBER(18,2),
        owner_name      VARCHAR(100),
        owner_email     VARCHAR(100),
        approved_by     VARCHAR(100),
        approved_date   DATE,
        version         INTEGER DEFAULT 1
    )""",

    # Table 4: Counterparty master - regulatory required
    """CREATE OR REPLACE TABLE COUNTERPARTY (
        counterparty_id VARCHAR(20)    NOT NULL PRIMARY KEY,
        counterparty_name VARCHAR(100),
        lei_code        VARCHAR(20),
        country         VARCHAR(50),
        credit_rating   VARCHAR(10),
        internal_limit_aud NUMBER(18,2),
        is_apra_regulated BOOLEAN,
        relationship_manager VARCHAR(100)
    )""",

    # View: Portfolio exposure by asset class - key for lineage
    """CREATE OR REPLACE VIEW VW_PORTFOLIO_EXPOSURE AS
    SELECT
        p.position_date,
        p.cost_center,
        p.gl_account,
        p.asset_class,
        p.book,
        SUM(p.net_exposure)     AS total_net_exposure,
        SUM(p.market_value_aud) AS total_market_value,
        SUM(p.pnl_daily)        AS total_pnl_daily,
        SUM(p.pnl_ytd)          AS total_pnl_ytd,
        SUM(p.var_1day)         AS total_var_1day,
        COUNT(*)                AS position_count
    FROM POSITION p
    GROUP BY p.position_date, p.cost_center, p.gl_account, p.asset_class, p.book""",

    # View: Trade P&L reconciliation vs position - cross-table lineage
    """CREATE OR REPLACE VIEW VW_TRADE_PNL_RECONCILIATION AS
    SELECT
        t.trade_date,
        t.cost_center,
        t.gl_account,
        t.asset_class,
        t.book,
        t.counterparty,
        SUM(t.market_value_aud)  AS trade_market_value,
        p.total_market_value     AS position_market_value,
        SUM(t.market_value_aud) - COALESCE(p.total_market_value, 0) AS reconciliation_break,
        p.total_pnl_daily        AS position_pnl,
        p.total_var_1day         AS var_exposure
    FROM TRADE t
    LEFT JOIN VW_PORTFOLIO_EXPOSURE p
           ON t.trade_date   = p.position_date
          AND t.cost_center  = p.cost_center
          AND t.gl_account   = p.gl_account
          AND t.asset_class  = p.asset_class
          AND t.book         = p.book
    GROUP BY t.trade_date, t.cost_center, t.gl_account, t.asset_class, t.book, t.counterparty,
             p.total_market_value, p.total_pnl_daily, p.total_var_1day""",
]

for sql in statements:
    label = sql.strip().split('\n')[0][:70]
    try:
        cur.execute(sql)
        print(f'OK: {label}')
    except Exception as e:
        print(f'ERR: {label}\n     {e}')

# Seed sample data
print('\nSeeding data...')

cur.execute("USE DATABASE APRA_RISK_DW")
cur.execute("USE SCHEMA RISK")

cur.execute("""INSERT INTO COUNTERPARTY VALUES
('CP001','Commonwealth Bank of Australia','213800WAVVOPS85N2205','Australia','AA-',500000000,true,'James Wu'),
('CP002','JPMorgan Chase Bank NA','8I5DZWZKVSZI1NUHU748','United States','A+',300000000,false,'Sarah Mitchell'),
('CP003','Macquarie Bank Limited','RBGKL3QSQFEP5KZNEC08','Australia','A',200000000,true,'David Park'),
('CP004','HSBC Bank plc','MP6I5ZYZBEU3UXPYFY54','United Kingdom','AA-',250000000,false,'Linda Nguyen'),
('CP005','ANZ Banking Group','ZU3ELRC57L3AEKXVLW38','Australia','AA-',400000000,true,'Michael Chen')
""")

cur.execute("""INSERT INTO BUDGET_PLAN VALUES
('BP2025-001',2025,null,'CC_RISK_001',610000,'Fixed Income',12000000,'Emma Thompson','e.thompson@bank.com.au','CFO Board',TO_DATE('2024-12-01'),1),
('BP2025-002',2025,null,'CC_RISK_001',620000,'Equities',8500000,'Emma Thompson','e.thompson@bank.com.au','CFO Board',TO_DATE('2024-12-01'),1),
('BP2025-003',2025,null,'CC_RISK_002',610000,'FX Derivatives',15000000,'Mark Sullivan','m.sullivan@bank.com.au','CFO Board',TO_DATE('2024-12-01'),1),
('BP2025-004',2025,null,'CC_RISK_002',630000,'Commodities',5000000,'Mark Sullivan','m.sullivan@bank.com.au','CFO Board',TO_DATE('2024-12-01'),1),
('BP2025-005',2025,null,'CC_TRADE_001',640000,'Fixed Income',20000000,'Priya Sharma','p.sharma@bank.com.au','CFO Board',TO_DATE('2024-12-01'),1)
""")

cur.execute("""INSERT INTO TRADE VALUES
('TRD-2025-001001',TO_DATE('2025-06-01'),TO_DATE('2025-06-03'),'CC_RISK_001',610000,'Fixed Income','AGB-10Y','AUS Govt Bond 10Y','CP001','Commonwealth Bank of Australia','BUY',50000000,50125000,'AUD','T001','Alex Kim','RATES_BOOK','SETTLED','MUREX'),
('TRD-2025-001002',TO_DATE('2025-06-01'),TO_DATE('2025-06-03'),'CC_RISK_001',620000,'Equities','BHP.AX','BHP Group Ltd','CP003','Macquarie Bank Limited','BUY',12000000,12340000,'AUD','T002','Jessica Lee','EQ_BOOK','SETTLED','MUREX'),
('TRD-2025-001003',TO_DATE('2025-06-02'),TO_DATE('2025-06-04'),'CC_RISK_002',610000,'FX Derivatives','AUDUSD-6M','AUDUSD 6M Forward','CP002','JPMorgan Chase Bank NA','SELL',25000000,24850000,'AUD','T003','Ryan Park','FX_BOOK','SETTLED','MUREX'),
('TRD-2025-001004',TO_DATE('2025-06-02'),TO_DATE('2025-06-04'),'CC_RISK_002',610000,'FX Derivatives','AUDUSD-3M','AUDUSD 3M Forward','CP004','HSBC Bank plc','BUY',10000000,10020000,'AUD','T003','Ryan Park','FX_BOOK','PENDING','MUREX'),
('TRD-2025-001005',TO_DATE('2025-06-03'),TO_DATE('2025-06-05'),'CC_TRADE_001',640000,'Fixed Income','AGB-5Y','AUS Govt Bond 5Y','CP005','ANZ Banking Group','BUY',75000000,75200000,'AUD','T004','Natalie Wong','RATES_BOOK','SETTLED','MUREX')
""")

cur.execute("""INSERT INTO POSITION VALUES
('POS-2025-0601-001',TO_DATE('2025-06-01'),'CC_RISK_001',610000,'RATES_BOOK','Fixed Income','AGB-10Y','AUS Govt Bond 10Y',50000000,0,50000000,50125000,125000,380000,1200000,420000,'AUD','MUREX'),
('POS-2025-0601-002',TO_DATE('2025-06-01'),'CC_RISK_001',620000,'EQ_BOOK','Equities','BHP.AX','BHP Group Ltd',12000000,0,12000000,12340000,340000,980000,2100000,95000,'AUD','MUREX'),
('POS-2025-0602-003',TO_DATE('2025-06-02'),'CC_RISK_002',610000,'FX_BOOK','FX Derivatives','AUDUSD-6M','AUDUSD 6M Forward',0,25000000,-25000000,24850000,-150000,-450000,-890000,210000,'AUD','MUREX'),
('POS-2025-0602-004',TO_DATE('2025-06-02'),'CC_RISK_002',610000,'FX_BOOK','FX Derivatives','AUDUSD-3M','AUDUSD 3M Forward',10000000,0,10000000,10020000,20000,60000,180000,85000,'AUD','MUREX'),
('POS-2025-0603-005',TO_DATE('2025-06-03'),'CC_TRADE_001',640000,'RATES_BOOK','Fixed Income','AGB-5Y','AUS Govt Bond 5Y',75000000,0,75000000,75200000,200000,600000,1800000,630000,'AUD','MUREX')
""")

conn.commit()
print('Data seeded OK')

# Verify
cur.execute("SELECT 'TRADE' as t, COUNT(*) FROM TRADE UNION ALL SELECT 'POSITION', COUNT(*) FROM POSITION UNION ALL SELECT 'BUDGET_PLAN', COUNT(*) FROM BUDGET_PLAN UNION ALL SELECT 'COUNTERPARTY', COUNT(*) FROM COUNTERPARTY")
for row in cur.fetchall():
    print(f'  {row[0]}: {row[1]} rows')

cur.execute("SELECT COUNT(*) FROM VW_PORTFOLIO_EXPOSURE")
print(f'  VW_PORTFOLIO_EXPOSURE: {cur.fetchone()[0]} rows')

cur.execute("SELECT COUNT(*) FROM VW_TRADE_PNL_RECONCILIATION")
print(f'  VW_TRADE_PNL_RECONCILIATION: {cur.fetchone()[0]} rows')

conn.close()
print('\nDone.')
