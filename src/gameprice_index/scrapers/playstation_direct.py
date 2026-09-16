"""PlayStation Direct (UK): Sony's own shop for physical games, read from its catalogue service."""

import logging
from typing import Any

from gameprice_index import config
from gameprice_index.scrapers.base import Scraper

logger = logging.getLogger(__name__)


class PlayStationDirectScraper(Scraper):
    name = "playstation-direct"
    source = "PlayStation Direct"

    def parse_product(self, product: dict[str, Any]) -> dict[str, Any]:
        """Turns one catalogue entry into a record."""
        stock = (product.get("stock") or {}).get("stockLevelStatus")
        badge = product.get("merchandisingBadge")
        if not badge and product.get("preOrderProduct"):
            badge = "PRE-ORDER"

        return self.record(
            name=product.get("name"),
            platform="PS5",
            product_code=product.get("code"),
            # the service only lists the current price; it has no field for a previous one
            price=(product.get("price") or {}).get("value"),
            badge=badge,
            out_of_stock=stock == "outOfStock" if stock else None,
            url=f"{config.PLAYSTATION_DIRECT_LINK_PREFIX}{product['url']}" if product.get("url") else None,
        )

    def fetch_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for page in range(config.PLAYSTATION_DIRECT_MAX_PAGES):
            payload = self.get_json(
                config.PLAYSTATION_DIRECT_API_URL,
                params={
                    "fields": "FULL",
                    "lang": "en_GB",
                    "currentPage": page,
                    "pageSize": config.PLAYSTATION_DIRECT_PAGE_SIZE,
                },
                headers={"Accept": "application/json"},
            )
            products = payload.get("products") or []
            records.extend(self.parse_product(product) for product in products)

            total_pages = (payload.get("pagination") or {}).get("totalPages", 1)
            logger.info(f"PlayStation Direct page {page + 1} of {total_pages}: {len(products)} items.")
            if not products or page + 1 >= total_pages or self.has_enough(records):
                break
        return records
