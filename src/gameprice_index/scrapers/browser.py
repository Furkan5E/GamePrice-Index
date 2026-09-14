"""Headless browser set-up for pages that only render their data with JavaScript."""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def setup_driver() -> webdriver.Chrome:
    """Configures and returns a headless Chrome WebDriver."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--log-level=3")  # suppress console clutter
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)
