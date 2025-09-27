# Currency ETL

## Overview
This repo implements a resilient ETL that fetches daily currency exchange rates from CNB, stores daily rows, and computes weekly averages.
________________________________________
## Quickstart
1. Create a Python virtualenv and install dependencies:

    python -m venv .venv
   
    source .venv/bin/activate

   pip install -r requirements.txt
________________________________________
2.	Edit config.yml to match your Postgres credentials and run type.
________________________________________
3.	Ensure Postgres is reachable and user has CREATE SCHEMA / CREATE TABLE rights.
________________________________________
4.	Run full load:
      python -m src --config config.yml --run_type full
  Or daily run (scheduled via cron or airflow):

  	Run Daily load:
  python -m src --config config.yml --run_type daily
________________________________________
