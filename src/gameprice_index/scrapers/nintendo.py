"""Nintendo eShop (UK): the Switch catalogue from the site's search index, priced by the eShop price service."""

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


def parse_price_entry(entry: dict[str, Any]) -> tuple[float, float | None, str | None] | None:
    """Returns (price, price_old, badge) from one price service entry, or None if it has no price."""
    regular = (entry.get("regular_price") or {}).get("raw_value")
    if regular is None:
        return None  # sales_status is "not_found" or "unreleased"

    badge = "PRE-ORDER" if entry.get("sales_status") == "preorder" else None
    discount = (entry.get("discount_price") or {}).get("raw_value")
    if discount is not None:
        return float(discount), float(regular), badge
    return float(regular), None, badge


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

    def fetch_prices(self, nsuids: list[str]) -> dict[str, tuple[float, float | None, str | None]]:
        """Looks up current prices in batches and maps each priced nsuid to (price, price_old, badge)."""
        prices = {}
        for start in range(0, len(nsuids), config.NINTENDO_PRICE_BATCH):
            batch = nsuids[start : start + config.NINTENDO_PRICE_BATCH]
            payload = self.get_json(
                config.NINTENDO_PRICE_URL,
                params={"country": config.NINTENDO_PRICE_COUNTRY, "lang": "en", "ids": ",".join(batch)},
            )
            for entry in payload.get("prices", []):
                parsed = parse_price_entry(entry)
                if parsed:
                    prices[str(entry["title_id"])] = parsed

        logger.info(f"Nintendo prices: {len(prices)} of {len(nsuids)} games priced.")
        return prices

    def fetch_records(self) -> list[dict[str, Any]]:
        docs = self.fetch_catalogue()
        if self.limit is not None:
            docs = docs[: self.limit]  # no point pricing games that will be cut off anyway

        nsuids = [nsuid for doc in docs if (nsuid := pick_nsuid(doc.get("nsuid_txt") or []))]
        prices = self.fetch_prices(nsuids)

        records = []
        for doc in docs:
            nsuid = pick_nsuid(doc.get("nsuid_txt") or [])
            title = (doc.get("title") or "").strip()
            if not nsuid or not title:
                continue

            # fall back to the index when the price service does not know the game
            price, price_old = index_price(doc)
            badge = None
            if nsuid in prices:
                price, price_old, badge = prices[nsuid]
            platforms = doc.get("system_names_txt") or []
            records.append(
                self.record(
                    name=title,
                    platform=platforms[0] if platforms else None,
                    url=f"{config.NINTENDO_LINK_PREFIX}{doc['url']}" if doc.get("url") else None,
                    product_code=nsuid,
                    price=price,
                    price_old=price_old,
                    badge=badge,
                )
            )
        return records
