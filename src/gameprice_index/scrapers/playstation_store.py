"""PlayStation Store (UK): the digital PS5 catalogue, read from the store's GraphQL service."""

import json
import logging
from typing import Any

from gameprice_index import config
from gameprice_index.scrapers.base import ScrapeError, Scraper

logger = logging.getLogger(__name__)


def parse_money(text: str | None, is_free: bool = False) -> float | None:
    """Converts a display price such as "£49.99" or "Free" into a number."""
    if is_free or (text and text.strip().lower() == "free"):
        return 0.0
    if not text:
        return None
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    return float(cleaned) if cleaned else None


class PlayStationStoreScraper(Scraper):
    name = "playstation"
    source = "PlayStation Store"

    def fetch_page(self, offset: int) -> dict[str, Any]:
        """Requests one page of the category grid, best sellers first."""
        variables = {
            "id": config.PLAYSTATION_STORE_CATEGORY_ID,
            "pageArgs": {"size": config.PLAYSTATION_STORE_PAGE_SIZE, "offset": offset},
            "sortBy": {"name": config.PLAYSTATION_STORE_SORT, "isAscending": False},
            "filterBy": list(config.PLAYSTATION_STORE_FILTERS),
            "facetOptions": [],
        }
        # the service only answers queries it already knows, identified by their hash
        extensions = {"persistedQuery": {"version": 1, "sha256Hash": config.PLAYSTATION_STORE_QUERY_HASH}}

        payload = self.get_json(
            config.PLAYSTATION_STORE_API_URL,
            params={
                "operationName": "categoryGridRetrieve",
                "variables": json.dumps(variables, separators=(",", ":")),
                "extensions": json.dumps(extensions, separators=(",", ":")),
            },
            headers={
                "x-psn-store-locale-override": config.PLAYSTATION_STORE_LOCALE,
                # the service rejects GETs without a content type as a cross-site request guard
                "content-type": "application/json",
            },
        )

        grid = (payload.get("data") or {}).get("categoryGridRetrieve")
        if not grid:
            raise ScrapeError(f"PlayStation Store returned no catalogue: {payload.get('errors') or payload}")
        return grid

    def parse_product(self, product: dict[str, Any]) -> dict[str, Any]:
        """Turns one catalogue entry into a record."""
        price_info = product.get("price") or {}
        is_free = bool(price_info.get("isFree"))
        base = parse_money(price_info.get("basePrice"), is_free)
        discounted = parse_money(price_info.get("discountedPrice"), is_free)

        # a subscriber-only discount is not the price most people pay
        if price_info.get("isTiedToSubscription") or discounted is None:
            discounted = base

        sku_types = {sku.get("type") for sku in product.get("skus") or []}
        return self.record(
            name=product.get("name"),
            platform="/".join(product.get("platforms") or []) or None,
            product_code=product.get("id"),
            price=discounted,
            price_old=base,
            badge="PRE-ORDER" if "PREORDER" in sku_types else None,
            url=f"{config.PLAYSTATION_STORE_LINK_PREFIX}{product['id']}" if product.get("id") else None,
        )

    def fetch_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        while True:
            grid = self.fetch_page(offset=len(records))
            products = grid.get("products") or []
            records.extend(self.parse_product(product) for product in products)

            page_info = grid.get("pageInfo") or {}
            logger.info(f"PlayStation Store: {len(records)} of {page_info.get('totalCount', '?')} games.")
            if not products or page_info.get("isLast", True) or self.has_enough(records):
                return records
