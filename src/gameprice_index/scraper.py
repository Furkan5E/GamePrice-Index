import logging
import time
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from gameprice_index import config

logger = logging.getLogger(__name__)


class ScrapeError(RuntimeError):
    """Raised when a source cannot be scraped or returns no items."""


def setup_driver() -> webdriver.Chrome:
    """Configures and returns a headless Chrome WebDriver."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--log-level=3")  # suppress console clutter
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def _text(tag: Tag | None) -> str | None:
    return tag.get_text(strip=True) if tag else None


def parse_nintendo_listing(html: str) -> list[dict[str, Any]]:
    """Extracts the base game records from the Nintendo listing page."""
    selectors = config.NINTENDO_SELECTORS
    soup = BeautifulSoup(html, "html.parser")

    nintendo_list = []
    for g in soup.select(selectors["tile"]):
        link_tag = g.select_one(selectors["link"])
        url_abs = f"{config.NINTENDO_LINK_PREFIX}{link_tag['href']}" if link_tag else None

        nintendo_list.append(
            {
                "name": _text(g.select_one(selectors["name"])),
                "platform": _text(g.select_one(selectors["platform"])),
                "url": url_abs,
                "nsuid": g.get("data-nsuid"),
                "price": None,
                "price_old": None,
                "badge": None,
                "date_range": None,
                "product_code": None,
                "out_of_stock": None,
                "source": "Nintendo",
            }
        )
    return nintendo_list


def scrape_nintendo_base(url: str) -> list[dict[str, Any]]:
    """Scrapes base game data from Nintendo using requests."""
    logger.info(f"Scraping Nintendo base data from: {url}")
    try:
        response = requests.get(url, headers=config.REQUEST_HEADERS, timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        # the page is utf-8 but sends no charset header, so requests guesses latin-1
        response.encoding = "utf-8"
        nintendo_list = parse_nintendo_listing(response.text)
    except Exception as e:
        raise ScrapeError(f"Failed to scrape Nintendo base data: {e}") from e

    if not nintendo_list:
        raise ScrapeError(f"No Nintendo games found at {url}; the page layout may have changed.")
    logger.info(f"Successfully extracted {len(nintendo_list)} base Nintendo items.")
    return nintendo_list


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


def parse_nintendo_prices(html: str) -> list[dict[str, Any]]:
    """Extracts the per-nsuid prices from the rendered Nintendo listing page."""
    selectors = config.NINTENDO_SELECTORS
    soup = BeautifulSoup(html, "html.parser")

    price_list = []
    for g in soup.select(selectors["tile"]):
        price, price_old = parse_nintendo_price(g.select_one(selectors["price_container"]))
        price_list.append({"nsuid": g.get("data-nsuid"), "price": price, "price_old": price_old})
    return price_list


def scrape_nintendo_prices(url: str) -> list[dict[str, Any]]:
    """Scrapes dynamic pricing data from Nintendo using Selenium."""
    logger.info(f"Scraping Nintendo pricing data via Selenium from: {url}")
    selectors = config.NINTENDO_SELECTORS
    driver = setup_driver()

    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, f"{selectors['price_container']} {selectors['regular_price']}")
            )
        )
        time.sleep(4)  # small delay

        price_list = parse_nintendo_prices(driver.page_source)
    except Exception as e:
        raise ScrapeError(f"Failed to scrape Nintendo prices: {e}") from e
    finally:
        driver.quit()

    if not price_list:
        raise ScrapeError(f"No Nintendo prices found at {url}; the page layout may have changed.")
    logger.info(f"Successfully extracted {len(price_list)} Nintendo price records.")
    return price_list


def parse_playstation_tiles(html: str) -> list[dict[str, Any]]:
    """Extracts every product tile from one page of the PlayStation listing."""
    selectors = config.PLAYSTATION_SELECTORS
    soup = BeautifulSoup(html, "html.parser")

    ps_list = []
    for g in soup.select(selectors["tile"]):
        link_tag = g.select_one(selectors["link"])
        price_tags = g.select(selectors["prices"])
        btn = g.select_one(selectors["product_code"])

        ps_list.append(
            {
                "name": _text(g.select_one(selectors["name"])),
                "price": price_tags[0].text.strip() if len(price_tags) >= 1 else None,
                "price_old": price_tags[1].text.strip() if len(price_tags) >= 2 else None,
                "badge": _text(g.select_one(selectors["badge"])),
                "date_range": _text(g.select_one(selectors["date_range"])),
                "url": link_tag["href"] if link_tag else None,
                "product_code": btn["data-product-code"] if btn else None,
                "out_of_stock": g.select_one(selectors["out_of_stock"]) is not None,
                "platform": "PS5",
                "nsuid": None,
                "source": "PlayStation",
            }
        )
    return ps_list


def scrape_playstation(url: str) -> list[dict[str, Any]]:
    """Scrapes PlayStation games and prices from every listing page using Selenium."""
    logger.info(f"Scraping PlayStation data via Selenium from: {url}")
    selectors = config.PLAYSTATION_SELECTORS
    driver = setup_driver()
    ps_list: list[dict[str, Any]] = []
    seen = set()

    try:
        driver.get(url)

        for page in range(1, config.PLAYSTATION_MAX_PAGES + 1):
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, selectors["any_tile"]))
            )
            time.sleep(2)

            # collect this page before moving on, skipping tiles already seen
            new_items = []
            for item in parse_playstation_tiles(driver.page_source):
                key = item["product_code"] or item["url"] or item["name"]
                if key not in seen:
                    seen.add(key)
                    new_items.append(item)
            ps_list.extend(new_items)
            logger.info(f"PlayStation page {page}: {len(new_items)} new items.")

            next_btns = driver.find_elements(By.CSS_SELECTOR, selectors["next_button"])
            if not new_items or not next_btns or not next_btns[0].is_enabled():
                break

            driver.execute_script("arguments[0].click();", next_btns[0])
            time.sleep(4)  # Polite delay
    except Exception as e:
        raise ScrapeError(f"Failed to scrape PlayStation data: {e}") from e
    finally:
        driver.quit()

    if not ps_list:
        raise ScrapeError(f"No PlayStation games found at {url}; the page layout may have changed.")
    logger.info(f"Successfully extracted {len(ps_list)} PlayStation items.")
    return ps_list
