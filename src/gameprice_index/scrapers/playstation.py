"""PlayStation Direct (UK): a paginated listing rendered entirely by JavaScript."""

import logging
from typing import Any

from bs4 import BeautifulSoup, Tag
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from gameprice_index import config
from gameprice_index.scrapers.base import Scraper
from gameprice_index.scrapers.browser import setup_driver

logger = logging.getLogger(__name__)


def _text(tag: Tag | None) -> str | None:
    return tag.get_text(strip=True) if tag else None


def parse_playstation_tiles(html: str) -> list[dict[str, Any]]:
    """Extracts every product tile from one page of the PlayStation listing."""
    selectors = config.PLAYSTATION_SELECTORS
    soup = BeautifulSoup(html, "html.parser")

    tiles = []
    for g in soup.select(selectors["tile"]):
        link_tag = g.select_one(selectors["link"])
        price_tags = g.select(selectors["prices"])
        btn = g.select_one(selectors["product_code"])

        tiles.append(
            {
                "name": _text(g.select_one(selectors["name"])),
                "price": price_tags[0].text.strip() if len(price_tags) >= 1 else None,
                "price_old": price_tags[1].text.strip() if len(price_tags) >= 2 else None,
                "badge": _text(g.select_one(selectors["badge"])),
                "url": link_tag["href"] if link_tag else None,
                "product_code": btn["data-product-code"] if btn else None,
                "out_of_stock": g.select_one(selectors["out_of_stock"]) is not None,
            }
        )
    return tiles


class PlayStationScraper(Scraper):
    name = "playstation"
    source = "PlayStation"

    def fetch_records(self) -> list[dict[str, Any]]:
        selectors = config.PLAYSTATION_SELECTORS
        records: list[dict[str, Any]] = []
        seen = set()

        driver = setup_driver()
        try:
            driver.get(config.PLAYSTATION_URL)
            wait = WebDriverWait(driver, config.SELENIUM_WAIT)

            for page in range(1, config.PLAYSTATION_MAX_PAGES + 1):
                wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selectors["any_tile"])))

                # collect this page before moving on, skipping tiles already seen
                new_items = 0
                for tile in parse_playstation_tiles(driver.page_source):
                    key = tile["product_code"] or tile["url"] or tile["name"]
                    if key not in seen:
                        seen.add(key)
                        records.append(self.record(platform="PS5", **tile))
                        new_items += 1
                logger.info(f"PlayStation page {page}: {new_items} new items.")

                next_btns = driver.find_elements(By.CSS_SELECTOR, selectors["next_button"])
                if not new_items or not next_btns or not next_btns[0].is_enabled():
                    break

                # the listing re-renders on page change, so the old first tile going stale marks the swap
                first_tile = driver.find_element(By.CSS_SELECTOR, selectors["any_tile"])
                driver.execute_script("arguments[0].click();", next_btns[0])
                wait.until(EC.staleness_of(first_tile))
        finally:
            driver.quit()

        return records
