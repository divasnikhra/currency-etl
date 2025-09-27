"""Responsible for making HTTP calls to CNB API with retries/backoff."""
from typing import Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..utils.logger import get_logger
from ..utils.exceptions import FetchError

logger = get_logger("fetcher")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(FetchError))
def fetch_for_date(endpoint: str, d, lang: str = "EN", timeout: int = 10) -> Optional[dict]:
    date_str = d.strftime("%Y-%m-%d")
    url = f"{endpoint}?date={date_str}&lang={lang}"
    try:
        logger.info("Fetching %s", date_str)
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        logger.info("Fetched %s rates for %s", len(payload.get("rates", [])), date_str)
        return payload
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", date_str, e)
        # raise to allow retry
        raise FetchError(e)
