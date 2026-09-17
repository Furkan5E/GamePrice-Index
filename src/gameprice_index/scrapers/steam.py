"""Steam (UK prices): top-selling PC games from the store's search results feed."""

import logging
from typing import Any

from bs4 import BeautifulSoup, Tag

from gameprice_index import config
from gameprice_index.scrapers.base import Scraper

logger = logging.getLogger(__name__)


def _pence(value: str | list[str] | None) -> float | None:
    """Steam sends prices as whole pence in data attributes."""
    if isinstance(value, str) and value.isdigit():
        return int(value) / 100
    return None


def parse_search_rows(html: str) -> list[dict[str, Any]]:
    """Extracts the games from one chunk of search results, skipping bundles and packages."""
    soup = BeautifulSoup(html, "html.parser")

    games = []
    for row in soup.select("a.search_result_row"):
        app_id = row.get("data-ds-appid")
        title = row.select_one("span.title")
        # bundles carry several comma-separated app ids, or none at all
        if not isinstance(app_id, str) or not app_id.isdigit() or title is None:
            continue

        price_block = row.select_one(".search_price_discount_combined")
        original = row.select_one(".discount_original_price")
        games.append(
            {
                "product_code": app_id,
                "name": title.get_text(strip=True),
                "price": _pence(price_block.get("data-price-final")) if price_block else None,
                "price_old": original.get_text(strip=True) if isinstance(original, Tag) else None,
                "url": str(row.get("href", "")).split("?")[0] or None,
            }
        )
    return games


class SteamScraper(Scraper):
    name = "steam"
    source = "Steam"

    def fetch_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        start = 0

        while True:
            payload = self.get_json(
                config.STEAM_SEARCH_URL,
                params={
                    "query": "",
                    "start": start,
                    "count": config.STEAM_PAGE_SIZE,
                    "cc": config.STEAM_COUNTRY,
                    "l": "english",
                    "category1": config.STEAM_CATEGORY_GAMES,
                    "filter": config.STEAM_FILTER,
                    "infinite": 1,  # ask for the JSON feed the page uses when scrolling
                },
            )
            rows_html = payload.get("results_html") or ""
            games = parse_search_rows(rows_html)

            # the ranking shifts while paging, so the same game can show up twice
            for game in games:
                if game["product_code"] not in seen:
                    seen.add(game["product_code"])
                    records.append(self.record(platform="PC", **game))

            start += config.STEAM_PAGE_SIZE
            total = payload.get("total_count", 0)
            logger.info(f"Steam: {len(records)} games after {min(start, total)} of {total} results.")
            if not rows_html.strip() or start >= total or self.has_enough(records):
                return records
