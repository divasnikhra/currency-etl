# Currency ETL

## Overview
This repository contains a robust ETL pipeline that fetches daily currency exchange rates from CNB, stores them in a Postgres database, and calculates weekly averages.

**Note:**  
- For a **quick overview**, see `currencyrate_etl.py`, which contains the full ETL logic in a single script.  
- For a **production-ready, orchestrated setup**, refer to `main.py` and the supporting modules in `src/`. These handle configuration, database operations, and workflow orchestration.

---

## Quickstart

1. **Set up Python environment**

Create a Python virtual environment and activate it. Install all dependencies from `requirements.txt`.

2. **Update configuration**

Edit `config.yml` to include your Postgres credentials, run type (`daily` or `full`), and other parameters.

3. **Prepare Postgres**

Ensure your Postgres database is reachable and that the user has privileges to create schemas and tables (`CREATE SCHEMA` / `CREATE TABLE`).

4. **Run ETL**

- **Full load**: runs a complete historical ETL and populates all available data.  
- **Daily load**: runs an incremental ETL for the current day; can be scheduled using cron, Task Scheduler, or Airflow.

---

## Notes

- The ETL uses **Postgres as the backend**, so ensure the database is running before execution.  
- Weekly averages are computed automatically from the daily data.  
- Logs and progress messages are printed to the console; logging to a file can be configured if desired.
