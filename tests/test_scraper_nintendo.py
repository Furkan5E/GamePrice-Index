import pytest
import requests
from bs4 import BeautifulSoup

from gameprice_index.scrapers import ScrapeError
from gameprice_index.scrapers.nintendo import (
    NintendoScraper,
    parse_nintendo_listing,
    parse_nintendo_price,
    parse_nintendo_prices,
)
from helpers import FakeSession


def _price_container(html: str):
    return BeautifulSoup(html, "html.parser").find("p", class_="price-small")


def test_parse_nintendo_price_regular():
    """A game that is not on sale has a price and no old price."""
    container = _price_container(
        '<p class="price-small"><span data-price="">£41.99</span><span class="discount" data-discount=""></span></p>'
    )
    assert parse_nintendo_price(container) == ("£41.99", None)


def test_parse_nintendo_price_on_sale():
    """The discount span holds the sale price, data-price the original one."""
    container = _price_container(
        '<p class="price-small"><span class="original-price" data-price="">£8.99</span>'
        '<span class="discount" data-discount="">£7.64*</span></p>'
    )
    assert parse_nintendo_price(container) == ("£7.64", "£8.99")


def test_parse_nintendo_price_missing():
    assert parse_nintendo_price(None) == (None, None)


def test_parse_nintendo_listing(load_fixture):
    games = parse_nintendo_listing(load_fixture("nintendo_listing.html"))

    assert len(games) == 5
    assert games[0] == {
        "name": "Star Fox",
        "platform": "Nintendo Switch 2",
        "url": "https://www.nintendo.co.uk/en-gb/Games/Nintendo-Switch-2-games/Star-Fox-3094728.html",
        "nsuid": "70010000123168",
    }


def test_parse_nintendo_listing_keeps_multi_edition_nsuids(load_fixture):
    """Games sold in several editions list every nsuid, separated by a pipe."""
    games = parse_nintendo_listing(load_fixture("nintendo_listing.html"))

    assert games[1]["nsuid"] == "70010000115568|70050000069174"
    assert games[1]["name"].startswith("Super Mario Bros. Wonder – Nintendo Switch 2 Edition")


def test_parse_nintendo_prices(load_fixture):
    prices = parse_nintendo_prices(load_fixture("nintendo_listing_rendered.html"))

    assert prices["70010000123168"] == ("£41.99", None)
    assert all(price for price, _ in prices.values())


def test_parse_nintendo_prices_on_sale(load_fixture):
    """Regression: the sale price is the current price and the struck-through one is the old price."""
    prices = parse_nintendo_prices(load_fixture("nintendo_listing_rendered.html"))
    on_sale = {nsuid: price for nsuid, price in prices.items() if price[1]}

    assert on_sale == {
        "70010000101676|70070000031399": ("£40.29", "£64.99"),
        "70010000126200": ("£2.99", "£5.39"),
    }


@pytest.fixture
def scraper(load_fixture, monkeypatch):
    """A Nintendo scraper whose listing and rendered prices both come from saved pages."""
    session = FakeSession({"nintendo.com": load_fixture("nintendo_listing_rendered.html")}, encoding="ISO-8859-1")
    scraper = NintendoScraper(session=session)
    monkeypatch.setattr(
        scraper, "fetch_prices", lambda: parse_nintendo_prices(load_fixture("nintendo_listing_rendered.html"))
    )
    return scraper


def test_scrape_joins_listing_and_prices(scraper):
    records = scraper.scrape()

    assert len(records) == 5
    assert records[0]["source"] == "Nintendo"
    assert records[0]["name"] == "Star Fox"
    assert records[0]["platform"] == "Nintendo Switch 2"
    assert records[0]["product_code"] == "70010000123168"
    assert (records[0]["price"], records[0]["price_old"]) == ("£41.99", None)


def test_scrape_uses_first_nsuid_as_product_code(scraper):
    """Multi-edition games carry several nsuids; the first is the base game."""
    wonder = scraper.scrape()[1]

    assert wonder["product_code"] == "70010000115568"
    assert wonder["price"] == "£16.99"


def test_scrape_decodes_utf8(scraper):
    """Regression: the page sends no charset, and names used to come back as mojibake."""
    wonder = scraper.scrape()[1]

    assert "Wonder – Nintendo Switch 2 Edition" in wonder["name"]


def test_scrape_sends_a_timeout(scraper):
    """A request without a timeout can hang the whole pipeline."""
    scraper.scrape()

    assert scraper.session.calls[0]["timeout"] > 0


def test_scrape_skips_tiles_without_nsuid(monkeypatch):
    """Regression: tiles with no nsuid used to end up with the literal id 'None'."""
    html = """
    <li class="page-list-group-item" data-nsuid="70010000096802"><p class="page-title">Mario Kart World</p></li>
    <li class="page-list-group-item" data-nsuid=""><p class="page-title">Farm 2+</p></li>
    """
    scraper = NintendoScraper(session=FakeSession({"nintendo.com": html}))
    monkeypatch.setattr(scraper, "fetch_prices", lambda: {"70010000096802": ("£66.99", None)})

    records = scraper.scrape()

    assert [record["name"] for record in records] == ["Mario Kart World"]
    assert records[0]["price"] == "£66.99"


def test_scrape_leaves_unpriced_games_empty(monkeypatch, load_fixture):
    scraper = NintendoScraper(session=FakeSession({"nintendo.com": load_fixture("nintendo_listing.html")}))
    monkeypatch.setattr(scraper, "fetch_prices", lambda: {})

    assert all(record["price"] is None for record in scraper.scrape())


def test_scrape_raises_on_network_error():
    scraper = NintendoScraper(session=FakeSession({"nintendo.com": requests.ConnectionError("boom")}))

    with pytest.raises(ScrapeError, match="Failed to scrape Nintendo"):
        scraper.scrape()


def test_scrape_raises_when_no_games_found():
    scraper = NintendoScraper(session=FakeSession({"nintendo.com": "<html></html>"}))

    with pytest.raises(ScrapeError, match="No Nintendo games found"):
        scraper.scrape()
