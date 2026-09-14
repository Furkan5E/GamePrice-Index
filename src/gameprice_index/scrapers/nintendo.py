"""Nintendo eShop (UK): static listing page plus prices rendered by JavaScript."""

import logging
from typing import Any

from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from gameprice_index import config
from gameprice_index.http_client import fetch
from gameprice_index.scrapers.base import Scraper
from gameprice_index.scrapers.browser import setup_driver

logger = logging.getLogger(__name__)


def _text(tag: Tag | None) -> str | None:
    return tag.get_text(strip=True) if tag else None


def parse_nintendo_listing(html: str) -> list[dict[str, Any]]:
    """Extracts name, platform, link and nsuid for every game on the listing page."""
    selectors = config.NINTENDO_SELECTORS
    soup = BeautifulSoup(html, "html.parser")

    games = []
    for g in soup.select(selectors["tile"]):
        link_tag = g.select_one(selectors["link"])
        games.append(
            {
                "name": _text(g.select_one(selectors["name"])),
                "platform": _text(g.select_one(selectors["platform"])),
                "url": f"{config.NINTENDO_LINK_PREFIX}{link_tag['href']}" if link_tag else None,
                "nsuid": g.get("data-nsuid"),
            }
        )
    return games


def parse_nintendo_price(price_container: Tag | None) -> tuple[str | None, str | None]:
    """Returns (price, price_old) from a Nintendo price element.

    The site renders the regular price in span[data-price] and, when a game is
    on sale, the reduced price in span.discount.
    """
    if not price_container:
        return None, None

    regular_tag = price_container.select_one(config.NINTENDO_SELECTORS["regular_price"])
    regular = regular_tag.get_text(strip=True).replace("*", "") if regular_tag else None

    sale_tag = price_container.select_one(config.NINTENDO_SELECTORS["sale_price"])
    sale = sale_tag.get_text(strip=True).replace("*", "") if sale_tag else None

    if sale:
        return sale, regular or None
    return regular or None, None


def parse_nintendo_prices(html: str) -> dict[str, tuple[str | None, str | None]]:
    """Maps each nsuid on the rendered listing page to its (price, price_old)."""
    selectors = config.NINTENDO_SELECTORS
    soup = BeautifulSoup(html, "html.parser")

    prices = {}
    for g in soup.select(selectors["tile"]):
        nsuid = g.get("data-nsuid")
        if nsuid:
            prices[str(nsuid)] = parse_nintendo_price(g.select_one(selectors["price_container"]))
    return prices


class NintendoScraper(Scraper):
    name = "nintendo"
    source = "Nintendo"

    def fetch_listing(self) -> list[dict[str, Any]]:
        """Downloads the static listing page with requests."""
        response = fetch(config.NINTENDO_URL, session=self.session)
        # the page is utf-8 but sends no charset header, so requests guesses latin-1
        response.encoding = "utf-8"
        return parse_nintendo_listing(response.text)

    def fetch_prices(self) -> dict[str, tuple[str | None, str | None]]:
        """Renders the listing page in a browser, because prices are filled in by a script."""
        selectors = config.NINTENDO_SELECTORS
        price_selector = f"{selectors['price_container']} {selectors['regular_price']}"
        driver = setup_driver()
        try:
            driver.get(config.NINTENDO_URL)

            # the price spans exist in the static HTML; wait until the page script has filled them in
            def prices_rendered(d: webdriver.Chrome) -> bool:
                return any(span.text.strip() for span in d.find_elements(By.CSS_SELECTOR, price_selector))

            WebDriverWait(driver, config.SELENIUM_WAIT).until(prices_rendered)
            return parse_nintendo_prices(driver.page_source)
        finally:
            driver.quit()

    def fetch_records(self) -> list[dict[str, Any]]:
        listing = self.fetch_listing()
        prices = self.fetch_prices() if listing else {}

        records = []
        for game in listing:
            nsuid = game["nsuid"]
            # listing tiles without an nsuid have no price record to join to
            if not nsuid:
                logger.warning(f"Skipping Nintendo tile without an nsuid: {game['name']}")
                continue

            price, price_old = prices.get(nsuid, (None, None))
            records.append(
                self.record(
                    name=game["name"],
                    platform=game["platform"],
                    url=game["url"],
                    # multi-edition games list several nsuids; the first is the base game
                    product_code=nsuid.split("|")[0],
                    price=price,
                    price_old=price_old,
                )
            )
        return records
