"""Nintendo eShop (UK): the whole Switch catalogue from the site's own search index."""

import logging
from typing import Any

from gameprice_index import config
from gameprice_index.scrapers.base import Scraper

logger = logging.getLogger(__name__)

# nsuids starting with 7001 are games; other prefixes are bundles, DLC and demos
GAME_NSUID_PREFIX = "7001"


def pick_nsuid(nsuids: list[str]) -> str | None:
    """Chooses the id of the base game from a listing that may carry several editions."""
    if not nsuids:
        return None
    return next((nsuid for nsuid in nsuids if nsuid.startswith(GAME_NSUID_PREFIX)), nsuids[0])


def _valid_price(value: float | None) -> float | None:
    """The index stores -1 for games that have no price yet."""
    return value if value is not None and value >= 0 else None


def index_price(doc: dict[str, Any]) -> tuple[float | None, float | None]:
    """Returns (price, price_old) as recorded in the search index."""
    regular = _valid_price(doc.get("price_regular_f"))
    lowest = _valid_price(doc.get("price_lowest_f"))
    if doc.get("price_has_discount_b") and lowest is not None:
        return lowest, regular
    return regular if regular is not None else lowest, None


class NintendoScraper(Scraper):
    name = "nintendo"
    source = "Nintendo"

    def fetch_catalogue(self) -> list[dict[str, Any]]:
        """Pages through the search index until it runs out or the limit is reached."""
        docs: list[dict[str, Any]] = []
        while True:
            page = self.get_json(
                config.NINTENDO_SEARCH_URL,
                params={
                    "q": "*",
                    "fq": config.NINTENDO_SEARCH_FILTER,
                    "fl": config.NINTENDO_SEARCH_FIELDS,
                    "sort": config.NINTENDO_SEARCH_SORT,
                    "rows": config.NINTENDO_PAGE_SIZE,
                    "start": len(docs),
                    "wt": "json",
                },
            )["response"]

            docs.extend(page["docs"])
            logger.info(f"Nintendo catalogue: {len(docs)} of {page['numFound']} games.")
            if not page["docs"] or len(docs) >= page["numFound"] or self.has_enough(docs):
                return docs

    def fetch_records(self) -> list[dict[str, Any]]:
        records = []
        for doc in self.fetch_catalogue():
            nsuid = pick_nsuid(doc.get("nsuid_txt") or [])
            title = (doc.get("title") or "").strip()
            if not nsuid or not title:
                continue

            price, price_old = index_price(doc)
            platforms = doc.get("system_names_txt") or []
            records.append(
                self.record(
                    name=title,
                    platform=platforms[0] if platforms else None,
                    url=f"{config.NINTENDO_LINK_PREFIX}{doc['url']}" if doc.get("url") else None,
                    product_code=nsuid,
                    price=price,
                    price_old=price_old,
                )
            )
        return records
