"""Loaders for daily and weekly tables.
Uses db.execute_values helper for efficient bulk loads.
"""
from typing import List
from ..utils.logger import get_logger
from ..db import execute_values
from ..utils.exceptions import DBError

logger = get_logger("loader")


def upsert_daily_rows(conn, schema: str, daily_table: str, df):
    if df is None or df.empty:
        logger.info("No daily rows to write")
        return 0
    records = df.to_dict("records")
    values = []
    for r in records:
        values.append((
            r["fetch_date"], r.get("country"), r.get("currency"), r.get("amount"), r.get("currencyCode"), r.get("rate"),
        ))
    query = f"""
    INSERT INTO {schema}.{daily_table}
    (fetch_date, country, currency, amount, currencyCode, rate)
    VALUES %s
    ON CONFLICT (fetch_date, currencyCode) DO UPDATE
    SET country=EXCLUDED.country,
        currency=EXCLUDED.currency,
        amount=EXCLUDED.amount,
        rate=EXCLUDED.rate,
        source_ts=now()
    """
    try:
        execute_values(conn, query, values)
        conn.commit()
        logger.info("Upserted %s daily rows", len(values))
        return len(values)
    except Exception as e:
        conn.rollback()
        logger.exception("Failed daily upsert")
        raise DBError(e)


def insert_weekly_rows(conn, schema: str, weekly_table: str, weekly_df, run_type: str = "daily"):
    if weekly_df is None or weekly_df.empty:
        logger.info("No weekly rows to insert")
        return 0
    values = []
    for r in weekly_df.itertuples(index=False):
        values.append((int(r.iso_year), int(r.iso_week), r.currencyCode, float(r.avg_rate), int(r.sample_count), r.week_start_date))

    try:
        if run_type == "full":
            # delete the weeks we are about to replace
            weeks = set((int(r.iso_year), int(r.iso_week)) for r in weekly_df.itertuples())
            logger.info("Full load: deleting existing rows for weeks: %s", weeks)
            cur = conn.cursor()
            for y, w in weeks:
                cur.execute(f"DELETE FROM {schema}.{weekly_table} WHERE iso_year=%s AND iso_week=%s", (y, w))
            cur.close()
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
        execute_values(conn, insert_q, values)
        conn.commit()
        logger.info("Inserted/Updated %s weekly rows", len(values))
        return len(values)
    except Exception as e:
        conn.rollback()
        logger.exception("Weekly insert failed")
        raise DBError(e)
