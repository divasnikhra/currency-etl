CREATE SCHEMA IF NOT EXISTS msd_financial_db;

CREATE TABLE IF NOT EXISTS msd_financial_db.currency_rates_daily (
    fetch_date DATE NOT NULL,
    country VARCHAR(128),
    currency VARCHAR(64),
    amount INTEGER,
    currencyCode VARCHAR(16) NOT NULL,
    rate NUMERIC(18,8),
    source_ts TIMESTAMP DEFAULT now(),
    PRIMARY KEY (fetch_date, currencyCode)
);

CREATE TABLE IF NOT EXISTS msd_financial_db.currency_rates_weekly_avg (
    iso_year INTEGER NOT NULL,
    iso_week INTEGER NOT NULL,
    currencyCode VARCHAR(16) NOT NULL,
    avg_rate NUMERIC(18,8) NOT NULL,
    sample_count INTEGER NOT NULL,
    week_start_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (iso_year, iso_week, currencyCode)
);

-- Index to speed up weekly lookups (optional)
CREATE INDEX IF NOT EXISTS idx_weekly_currency ON msd_financial_db.currency_rates_weekly_avg(currencyCode);
