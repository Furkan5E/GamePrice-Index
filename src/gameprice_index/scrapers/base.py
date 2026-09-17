"""The contract every storefront scraper follows."""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import requests

from gameprice_index import config
from gameprice_index.http_client import build_session, fetch

logger = logging.getLogger(__name__)

# every scraper returns records with exactly these keys
RECORD_FIELDS = (
    "source",
    "platform",
    "product_code",
    "name",
    "price",
    "price_old",
    "badge",
    "out_of_stock",
    "url",
)


class ScrapeError(RuntimeError):
    """Raised when a source cannot be scraped or returns no items."""


class Scraper(ABC):
    """Fetches the current catalogue of one storefront as a list of records.

    Subclasses set `name` (the key used on the command line and in file names)
    and `source` (the label stored with every record), and implement
    `fetch_records`. Callers use `scrape`, which adds the shared error handling.
    """

    name: ClassVar[str]
    source: ClassVar[str]

    def __init__(self, session: requests.Session | None = None, limit: int | None = None) -> None:
        self.session = session
        self.limit = limit

    @abstractmethod
    def fetch_records(self) -> list[dict[str, Any]]:
        """Returns one record per product, built with `self.record`."""

    def _request_json(self, method: str, url: str, **kwargs: Any) -> Any:
        """Requests a JSON document through the shared retrying session, pausing briefly afterwards."""
        if self.session is None:
            self.session = build_session()

        response = fetch(url, session=self.session, method=method, **kwargs)
        if config.REQUEST_DELAY:
            time.sleep(config.REQUEST_DELAY)
        return response.json()

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self._request_json("GET", url, **kwargs)

    def post_json(self, url: str, **kwargs: Any) -> Any:
        return self._request_json("POST", url, **kwargs)

    def has_enough(self, records: list[dict[str, Any]]) -> bool:
        """True once the limit is reached, so paging can stop early."""
        return self.limit is not None and len(records) >= self.limit

    def record(self, **fields: Any) -> dict[str, Any]:
        """Builds a record with every expected key, filling the ones a source does not provide."""
        unknown = set(fields) - set(RECORD_FIELDS)
        if unknown:
            raise KeyError(f"Unknown record fields: {sorted(unknown)}")

        record: dict[str, Any] = dict.fromkeys(RECORD_FIELDS)
        record["source"] = self.source
        record.update(fields)
        return record

    def scrape(self) -> list[dict[str, Any]]:
        """Fetches the records, turning any failure or an empty result into a ScrapeError."""
        logger.info(f"Scraping {self.source}...")
        try:
            records = self.fetch_records()
        except ScrapeError:
            raise
        except Exception as e:
            raise ScrapeError(f"Failed to scrape {self.source}: {e}") from e

        if not records:
            raise ScrapeError(f"No {self.source} games found; the site layout may have changed.")
        if self.limit is not None:
            records = records[: self.limit]

        logger.info(f"Successfully extracted {len(records)} {self.source} items.")
        return records
