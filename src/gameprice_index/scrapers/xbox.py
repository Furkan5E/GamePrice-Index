"""Xbox store (UK): the games browse listing, read from the service behind xbox.com."""

import logging
import uuid
from typing import Any

from gameprice_index import config
from gameprice_index.scrapers.base import Scraper

logger = logging.getLogger(__name__)


def pick_price(product: dict[str, Any]) -> tuple[float | None, float | None]:
    """Returns (price, price_old) from the first purchasable offer, or (None, None) if there is none."""
    offers = (product.get("specificPrices") or {}).get("purchaseable") or []
    if not offers:
        return None, None
    return offers[0].get("listPrice"), offers[0].get("msrp")


class XboxScraper(Scraper):
    name = "xbox"
    source = "Xbox"

    def fetch_page(self, continuation: str | None) -> dict[str, Any]:
        """Requests one page of the browse listing; the token from the previous page asks for the next."""
        body: dict[str, Any] = {
            "Filters": config.XBOX_FILTERS,
            "ReturnFilters": False,
            "ChannelKeyToBeUsedInResponse": config.XBOX_CHANNEL_KEY,
        }
        if continuation:
            body["EncodedCT"] = continuation

        return self.post_json(
            config.XBOX_BROWSE_URL,
            params={"locale": config.XBOX_LOCALE},
            json=body,
            headers={
                "x-ms-api-version": "1.1",
                # a correlation id the service insists on; any fresh value will do
                "ms-cv": f"{uuid.uuid4().hex[:16]}.1",
                "Xbox-Market": config.XBOX_MARKET,
                "Xbox-Language": config.XBOX_LOCALE,
                "Origin": "https://www.xbox.com",
            },
        )

    def parse_product(self, product: dict[str, Any]) -> dict[str, Any]:
        """Turns one product summary into a record."""
        price, price_old = pick_price(product)
        product_id = product.get("productId")
        return self.record(
            name=product.get("title"),
            platform="Xbox",
            product_code=product_id,
            price=price,
            price_old=price_old,
            url=f"{config.XBOX_LINK_PREFIX}{product_id}" if product_id else None,
        )

    def fetch_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        continuation = None

        for _ in range(config.XBOX_MAX_PAGES):
            payload = self.fetch_page(continuation)
            channel = (payload.get("channels") or {}).get(config.XBOX_CHANNEL_KEY) or {}
            products = payload.get("productSummaries") or []

            records.extend(self.parse_product(product) for product in products if product.get("productKind") == "Game")

            continuation = channel.get("encodedCT")
            logger.info(f"Xbox: {len(records)} of {channel.get('totalItems', '?')} games.")
            if not products or not continuation or self.has_enough(records):
                break
        return records
