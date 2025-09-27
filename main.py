"""Orchestration script. Loads config, runs fetch -> transform -> load."""
import argparse
import yaml
from datetime import date, timedelta
from dateutil import parser as date_parser
from src.utils.logger import get_logger
from src.db import get_conn, apply_ddl
from src.etl.fetcher import fetch_for_date
from src.etl.transformer import build_dataframe, compute_weekly_averages_from_df
from src.etl.loader import upsert_daily_rows, insert_weekly_rows

logger = get_logger("main")


def get_dates_for_run(run_cfg):
    run_type = run_cfg.get("run_type", "daily").lower()
    if run_type == "daily":
        today = date.today()
        logger.info("Run type = daily. Will fetch for %s", today)
        return [today]
    elif run_type == "full":
        start = date_parser.parse(run_cfg["start_date"]).date()
        end = date_parser.parse(run_cfg["end_date"]).date()
        days = []
        cur = start
        while cur <= end:
            days.append(cur)
            cur += timedelta(days=1)
        logger.info("Run type = full. Will fetch %s days (%s to %s)", len(days), start, end)
        return days
    else:
        raise ValueError("Unsupported run_type in config")


def run(cfg_path: str, run_type: str = None):
    with open(cfg_path) as fh:
        cfg = yaml.safe_load(fh)

    if run_type:
        cfg["run"]["run_type"] = run_type

    api_cfg = cfg["api"]
    db_cfg = cfg["db"]
    run_cfg = cfg["run"]

    dates = get_dates_for_run(run_cfg)

    payloads = []
    for d in dates:
        try:
            payload = fetch_for_date(api_cfg["endpoint"], d, api_cfg.get("lang", "EN"), timeout=api_cfg.get("timeout_seconds", 10))
            payloads.append(payload)
        except Exception:
            logger.exception("Fetch failure for %s. Skipping this date.", d)
            continue

    df = build_dataframe(payloads)
    weekly_df = compute_weekly_averages_from_df(df)

    # DB operations
    from pathlib import Path
    ddl_sql = Path(__file__).parent.joinpath("ddl/ddl.sql").read_text()
    with get_conn(db_cfg) as conn:
        apply_ddl(conn, ddl_sql)
        upsert_daily_rows(conn, db_cfg["schema"], db_cfg["daily_table"], df)
        insert_weekly_rows(conn, db_cfg["schema"], db_cfg["weekly_table"], weekly_df, run_type=run_cfg["run_type"])

    logger.info("ETL run completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Currency ETL runner")
    parser.add_argument("--config", default="config.yml", help="Path to config.yml")
    parser.add_argument("--run_type", choices=["daily", "full"], help="Override run_type")
    args = parser.parse_args()
    run(args.config, run_type=args.run_type)
