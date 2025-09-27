"""Transform raw API payloads into DataFrames and compute weekly aggregates."""
from datetime import date, timedelta
import pandas as pd
from typing import List
from ..utils.logger import get_logger

logger = get_logger("transformer")


def build_dataframe(payloads: List[dict]):
    rows = []
    for p in payloads:
        if not p or "rates" not in p:
            continue
        fetch_date = p.get("date")
        if fetch_date is None:
            # Try to get from first rate's 'validFor'
            rates = p.get("rates", [])
            if rates and rates[0].get("validFor"):
                fetch_date = rates[0]["validFor"]
            else:
                logger.warning("Skipping payload with missing fetch_date: %s", p)
                continue
        # payload may have 'date' as string; normalize
        for r in p.get("rates", []):
            try:
                rows.append({
                    "fetch_date": pd.to_datetime(fetch_date).date(),
                    "country": r.get("country"),
                    "currency": r.get("currency"),
                    "amount": int(r.get("amount")) if r.get("amount") is not None else None,
                    "currencyCode": r.get("currencyCode"),
                    "rate": float(str(r.get("rate")).replace(",", ".")) if r.get("rate") is not None else None,
                })
            except Exception:
                # skip problematic row but log
                logger.exception("Skipping bad rate row for payload: %s", r)
                continue
    df = pd.DataFrame(rows)
    logger.info("DataFrame built with %s rows", len(df))
    return df


def compute_weekly_averages_from_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["fetch_date"] = pd.to_datetime(df["fetch_date"]).dt.date
    df["iso_year"] = df["fetch_date"].apply(lambda d: d.isocalendar()[0])
    df["iso_week"] = df["fetch_date"].apply(lambda d: d.isocalendar()[1])
    df = df[df["rate"].notnull() & df["currencyCode"].notnull()]
    grouped = df.groupby(["iso_year", "iso_week", "currencyCode"], as_index=False).agg(
        avg_rate=("rate", "mean"),
        sample_count=("rate", "count"),
    )

    def iso_week_start(y, w):
        jan4 = date(y, 1, 4)
        start = jan4 - timedelta(days=jan4.isoweekday() - 1)
        return (start + timedelta(weeks=w - 1))

    grouped["week_start_date"] = grouped.apply(lambda r: iso_week_start(int(r["iso_year"]), int(r["iso_week"])), axis=1)
    grouped["avg_rate"] = grouped["avg_rate"].round(8)
    logger.info("Computed weekly averages: %s rows", len(grouped))
    return grouped
