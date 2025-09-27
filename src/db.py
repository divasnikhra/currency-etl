"""Database helpers: connection, apply DDL and safe execution helpers."""
from contextlib import contextmanager
import psycopg2
import psycopg2.extras
import yaml
from typing import Dict
from .utils.logger import get_logger
from .utils.exceptions import DBError

logger = get_logger("db")

def load_db_config(cfg: Dict):
    return cfg["db"]

@contextmanager
def get_conn(db_cfg: Dict):
    """Yield a psycopg2 connection and ensure cleanup. Caller decides commit/rollback."""
    conn = None
    try:
        logger.info("Connecting to Postgres as %s@%s:%s/%s", db_cfg["user"], db_cfg["host"], db_cfg["port"], db_cfg["dbname"])
        conn = psycopg2.connect(
            host=db_cfg["host"],
            port=db_cfg["port"],
            dbname=db_cfg["dbname"],
            user=db_cfg["user"],
            password=db_cfg["password"],
        )
        conn.autocommit = False
        yield conn
    except Exception as e:
        logger.exception("DB connection error")
        raise DBError(e)
    finally:
        if conn:
            conn.close()
            logger.info("DB connection closed")


def apply_ddl(conn, ddl_sql: str):
    cur = conn.cursor()
    try:
        logger.info("Applying DDL...")
        cur.execute(ddl_sql)
        conn.commit()
        logger.info("DDL applied successfully")
    except Exception as e:
        conn.rollback()
        logger.exception("Failed to apply DDL")
        raise DBError(e)
    finally:
        cur.close()


def execute_values(conn, insert_query: str, values: list):
    cur = conn.cursor()
    try:
        psycopg2.extras.execute_values(cur, insert_query, values, page_size=100)
    except Exception as e:
        logger.exception("execute_values failed")
        raise DBError(e)
    finally:
        cur.close()
