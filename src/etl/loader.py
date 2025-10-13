"""Loaders for daily and weekly tables.
Uses db.execute_values helper for efficient bulk loads.
"""

from typing import List
from ..utils.logger import get_logger
from ..db import execute_values
from ..utils.exceptions import DBError
import pandas as pd

logger = get_logger("loader")


def upsert_daily_rows(conn, schema: str, daily_table: str, df: pd.DataFrame):
    """
    Upserts daily currency rows into the target table.
    Deduplicates rows by (fetch_date, currencyCode) before bulk insert.
    """

    if df is None or df.empty:
        logger.info("No daily rows to write")
        return 0

    # ✅ Fix: remove duplicates to avoid ON CONFLICT issue
    dupes = df[df.duplicated(subset=["fetch_date", "currencyCode"], keep=False)]
    if not dupes.empty:
        logger.warning("Found %d duplicate key rows in daily data. They were dropped.", len(dupes))

    df = df.drop_duplicates(subset=["fetch_date", "currencyCode"], keep="last")

    records = df.to_dict("records")
    values = [
        (
            r["fetch_date"],
            r.get("country"),
            r.get("currency"),
            r.get("amount"),
            r.get("currencyCode"),
            r.get("rate"),
        )
        for r in records
    ]

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
        logger.info("Upserted %d daily rows successfully", len(values))
        return len(values)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            logger.exception("Failed to rollback after daily upsert error")
        logger.exception("Error while upserting daily rows")
        raise DBError(e)


def insert_weekly_rows(conn, schema: str, weekly_table: str, weekly_df: pd.DataFrame, run_type: str = "daily"):
    """
    Inserts weekly aggregated rows into the target table.
    Deduplicates rows by (iso_year, iso_week, currencyCode).
    In 'full' mode, deletes existing weekly entries before inserting.
    """

    if weekly_df is None or weekly_df.empty:
        logger.info("No weekly rows to insert")
        return 0

    # ✅ Fix: remove duplicates within weekly_df
    dupes = weekly_df[weekly_df.duplicated(subset=["iso_year", "iso_week", "currencyCode"], keep=False)]
    if not dupes.empty:
        logger.warning("Found %d duplicate weekly key rows. They were dropped.", len(dupes))

    weekly_df = weekly_df.drop_duplicates(subset=["iso_year", "iso_week", "currencyCode"], keep="last")

    # build values from dict records to avoid pandas scalar typing issues
    records = weekly_df.to_dict("records")
    values = []
    for r in records:
        # keep native values; psycopg2 will convert Python types (including numpy scalars)
        values.append(
            (
                r.get("iso_year"),
                r.get("iso_week"),
                r.get("currencyCode"),
                r.get("avg_rate"),
                r.get("sample_count"),
                r.get("week_start_date"),
            )
        )

    try:
        if run_type == "full":
            # Delete existing rows for the same weeks before inserting
            weeks = set((r.get("iso_year"), r.get("iso_week")) for r in records)
            logger.info("Full load: deleting existing rows for weeks: %s", weeks)
            cur = conn.cursor()
            for y, w in weeks:
                cur.execute(
                    f"DELETE FROM {schema}.{weekly_table} WHERE iso_year=%s AND iso_week=%s",
                    (y, w),
                )
            cur.close()

        insert_q = f"""
        INSERT INTO {schema}.{weekly_table}
        (iso_year, iso_week, currencyCode, avg_rate, sample_count, week_start_date)
        VALUES %s
        ON CONFLICT (iso_year, iso_week, currencyCode) DO UPDATE
        SET avg_rate = EXCLUDED.avg_rate,
            sample_count = EXCLUDED.sample_count,
            week_start_date = EXCLUDED.week_start_date,
            created_at = now()
        """

        execute_values(conn, insert_q, values)
        conn.commit()
        logger.info("Inserted %d weekly rows successfully", len(values))
        return len(values)

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            logger.exception("Failed to rollback after weekly insert error")
        logger.exception("Error while inserting weekly rows")
        raise DBError(e)
