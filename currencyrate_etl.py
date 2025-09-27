"""
This is for testing purpose and not part of actual code
Single-file ETL script for Visual Studio (VS Code)
Fetches currency rates daily/full, inserts into Postgres, computes weekly averages.
"""

import requests
import pandas as pd
import psycopg2
import psycopg2.extras
from datetime import datetime, date, timedelta
from dateutil import parser as date_parser

# ---------------- Config inline ----------------
CONFIG = {
    "api": {
        "endpoint": "https://api.cnb.cz/cnbapi/exrates/daily",
        "lang": "EN"
    },
    "db": {
        "host": "localhost",
        "port": 5432,
        "dbname": "postgres",
        "user": "postgres",
        "password": "admin",
        "schema": "msd_financial_db",
        "daily_table": "currency_rates_daily",
        "weekly_table": "currency_rates_weekly_avg"
    },
    "run": {
        "run_type": "full",  # daily or full
        "start_date": "2025-09-01",
        "end_date": "2025-09-27"
    }
}

# ---------------- DDL inline ----------------
DDL = """
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
"""

# ---------------- Helpers ----------------
def get_conn(db_cfg):
    print("🔌 Connecting to Postgres...")
    conn = psycopg2.connect(
        host=db_cfg["host"],
        port=db_cfg["port"],
        dbname=db_cfg["dbname"],
        user=db_cfg["user"],
        password=db_cfg["password"]
    )
    conn.autocommit = False
    print("✅ Connected to Postgres")
    return conn

def apply_ddl_if_needed(conn):
    print("📄 Applying DDL (create schema/tables if not exists)...")
    cur = conn.cursor()
    try:
        cur.execute(DDL)
        conn.commit()
        print("✅ DDL applied.")
    except Exception as e:
        conn.rollback()
        print("❌ Failed to apply DDL:", e)
        raise
    finally:
        cur.close()

def get_dates_for_run(run_cfg):
    run_type = run_cfg.get("run_type", "daily").lower()
    if run_type == "daily":
        today = date.today()
        print(f"📅 Run type = daily. Will fetch for {today}")
        return [today]
    elif run_type == "full":
        start = date_parser.parse(run_cfg["start_date"]).date()
        end = date_parser.parse(run_cfg["end_date"]).date()
        days = []
        cur = start
        while cur <= end:
            days.append(cur)
            cur += timedelta(days=1)
        print(f"📅 Run type = full. Will fetch {len(days)} days ({start} to {end})")
        return days
    else:
        raise ValueError("Unsupported run_type in config")

def fetch_data_for_date(endpoint, date_obj, lang="EN", timeout=10):
    date_str = date_obj.strftime("%Y-%m-%d")
    url = f"{endpoint}?date={date_str}&lang={lang}"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        print(f"✅ Fetched {len(data.get('rates', []))} rates for {date_str}")
        return data
    except Exception as e:
        print(f"⚠️ Failed to fetch for {date_str}: {e}")
        return None

def build_dataframe(dates, api_cfg):
    all_rows = []
    for d in dates:
        data = fetch_data_for_date(api_cfg["endpoint"], d, api_cfg.get("lang", "EN"))
        if not data or "rates" not in data:
            continue
        for r in data["rates"]:
            try:
                rate = float(str(r.get("rate")).replace(",", "."))
            except Exception:
                rate = None
            all_rows.append({
                "fetch_date": d,
                "country": r.get("country"),
                "currency": r.get("currency"),
                "amount": int(r.get("amount")),
                "currencyCode": r.get("currencyCode"),
                "rate": rate
            })
    df = pd.DataFrame(all_rows)
    print(f"✅ DataFrame created with {len(df)} rows")
    if not df.empty:
        print(df.head())
    return df

def upsert_daily_rows(conn, schema, daily_table, df):
    if df.empty:
        print("ℹ️ No daily rows to write.")
        return
    records = df.to_dict("records")
    values = []
    now = datetime.utcnow()
    for r in records:
        values.append((r["fetch_date"], r["country"], r["currency"], r["amount"], r["currencyCode"], r["rate"], now))
    cur = conn.cursor()
    try:
        query = f"""
        INSERT INTO {schema}.{daily_table}
        (fetch_date, country, currency, amount, currencyCode, rate, source_ts)
        VALUES %s
        ON CONFLICT (fetch_date, currencyCode) DO UPDATE
        SET country=EXCLUDED.country,
            currency=EXCLUDED.currency,
            amount=EXCLUDED.amount,
            rate=EXCLUDED.rate,
            source_ts=EXCLUDED.source_ts
        """
        psycopg2.extras.execute_values(cur, query, values, page_size=100)
        conn.commit()
        print(f"✅ Upserted {len(values)} daily rows")
    except Exception as e:
        conn.rollback()
        print("❌ Failed daily upsert:", e)
        raise
    finally:
        cur.close()

def compute_weekly_averages_from_df(df):
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["fetch_date"] = pd.to_datetime(df["fetch_date"]).dt.date
    df["iso_year"] = df["fetch_date"].apply(lambda d: d.isocalendar()[0])
    df["iso_week"] = df["fetch_date"].apply(lambda d: d.isocalendar()[1])
    df = df[df["rate"].notnull() & df["currencyCode"].notnull()]
    grouped = df.groupby(["iso_year","iso_week","currencyCode"], as_index=False).agg(
        avg_rate=("rate","mean"),
        sample_count=("rate","count")
    )
    def iso_week_start(y, w):
        jan4 = date(y,1,4)
        start = jan4 - timedelta(days=jan4.isoweekday()-1)
        return (start + timedelta(weeks=w-1))
    grouped["week_start_date"] = grouped.apply(lambda r: iso_week_start(int(r["iso_year"]), int(r["iso_week"])), axis=1)
    grouped["avg_rate"] = grouped["avg_rate"].round(8)
    print(f"✅ Computed weekly averages: {len(grouped)} rows")
    return grouped

def insert_weekly_rows(conn, schema, weekly_table, weekly_df, run_type="daily"):
    if weekly_df.empty:
        print("ℹ️ No weekly rows to insert.")
        return
    cur = conn.cursor()
    try:
        if run_type == "full":
            weeks = set((int(r.iso_year), int(r.iso_week)) for r in weekly_df.itertuples())
            print(f"🗑️ Full load: replacing weeks {weeks}")
            for y,w in weeks:
                cur.execute(f"DELETE FROM {schema}.{weekly_table} WHERE iso_year=%s AND iso_week=%s", (y,w))
        values = []
        for r in weekly_df.itertuples():
            values.append((r.iso_year, r.iso_week, r.currencyCode, r.avg_rate, r.sample_count, r.week_start_date))
        insert_q = f"""
        INSERT INTO {schema}.{weekly_table}
        (iso_year, iso_week, currencyCode, avg_rate, sample_count, week_start_date)
        VALUES %s
        ON CONFLICT (iso_year, iso_week, currencyCode) DO UPDATE
        SET avg_rate=EXCLUDED.avg_rate,
            sample_count=EXCLUDED.sample_count,
            week_start_date=EXCLUDED.week_start_date,
            created_at=now()
        """
        psycopg2.extras.execute_values(cur, insert_q, values, page_size=100)
        conn.commit()
        print(f"✅ Inserted/Updated {len(values)} weekly rows")
    except Exception as e:
        conn.rollback()
        print("❌ Weekly insert failed:", e)
        raise
    finally:
        cur.close()

# ---------------- Main ----------------
def run():
    api_cfg = CONFIG["api"]
    db_cfg = CONFIG["db"]
    run_cfg = CONFIG["run"]

    dates = get_dates_for_run(run_cfg)
    df = build_dataframe(dates, api_cfg)

    conn = get_conn(db_cfg)
    try:
        apply_ddl_if_needed(conn)
        upsert_daily_rows(conn, db_cfg["schema"], db_cfg["daily_table"], df)
        weekly_df = compute_weekly_averages_from_df(df)
        insert_weekly_rows(conn, db_cfg["schema"], db_cfg["weekly_table"], weekly_df, run_type=run_cfg["run_type"])
        print("🏁 ETL completed successfully.")
    finally:
        conn.close()
        print("🔒 DB connection closed.")

# VS-friendly entry point
if __name__ == "__main__":
    run()
