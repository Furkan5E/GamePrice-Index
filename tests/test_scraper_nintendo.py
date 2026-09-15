import json

import pytest
import requests

from gameprice_index import config
from gameprice_index.scrapers import ScrapeError
from gameprice_index.scrapers.nintendo import NintendoScraper, index_price, pick_nsuid
from helpers import FakeSession


@pytest.fixture
def search_pages(load_fixture):
    """Two saved pages of the search index: four games, then two."""
    return [json.loads(load_fixture(f"nintendo_search_page{n}.json")) for n in (1, 2)]


@pytest.fixture
def session(search_pages, monkeypatch):
    """Serves the saved search pages according to the `start` offset that was asked for."""
    monkeypatch.setattr(config, "NINTENDO_PAGE_SIZE", 4)

    def search(url, params=None, **kwargs):
        return search_pages[0] if params["start"] == 0 else search_pages[1]

    return FakeSession({"searching.nintendo-europe.com": search})


def test_pick_nsuid_prefers_the_base_game():
    """Multi-edition listings carry several ids; the 7001 one is the game itself."""
    assert pick_nsuid(["70070000019472", "70010000062277"]) == "70010000062277"
    assert pick_nsuid(["70070000019472"]) == "70070000019472"
    assert pick_nsuid([]) is None


def test_index_price_regular():
    assert index_price({"price_regular_f": 49.99, "price_lowest_f": 49.99, "price_has_discount_b": False}) == (
        49.99,
        None,
    )


def test_index_price_on_sale():
    """Regression: the sale price is the current price and the regular price is the old one."""
    doc = {"price_regular_f": 24.99, "price_lowest_f": 3.74, "price_has_discount_b": True}

    assert index_price(doc) == (3.74, 24.99)


def test_index_price_missing():
    assert index_price({}) == (None, None)


def test_index_price_treats_minus_one_as_unpriced():
    """The index marks unreleased games with a price of -1, which must not reach the dataset."""
    assert index_price({"price_regular_f": -1.0, "price_lowest_f": -1.0}) == (None, None)


def test_scrape_pages_through_the_whole_catalogue(session):
    records = NintendoScraper(session=session).scrape()

    assert len(records) == 6
    assert [call["params"]["start"] for call in session.calls] == [0, 4]
    assert records[0] == {
        "source": "Nintendo",
        "platform": "Nintendo Switch 2",
        "product_code": "70010000130793",
        "name": "The Legend of Zelda: Ocarina of Time",
        "price": 49.99,
        "price_old": None,
        "badge": None,
        "out_of_stock": None,
        "url": "https://www.nintendo.com/en-gb/Games/Nintendo-Switch-2-games/The-Legend-of-Zelda-Ocarina-of-Time-3115664.html",
    }


def test_scrape_reads_sale_prices(session):
    street_fighter = NintendoScraper(session=session).scrape()[3]

    assert street_fighter["name"] == "Street Fighter™ 30th Anniversary Collection"
    assert (street_fighter["price"], street_fighter["price_old"]) == (3.74, 24.99)


def test_scrape_uses_the_base_game_id(session):
    hogwarts = NintendoScraper(session=session).scrape()[4]

    assert hogwarts["name"] == "Hogwarts Legacy"
    assert hogwarts["product_code"] == "70010000062277"


def test_scrape_keeps_free_games(session):
    free = NintendoScraper(session=session).scrape()[5]

    assert free["price"] == 0
    assert free["price_old"] is None


def test_scrape_stops_paging_at_the_limit(session):
    records = NintendoScraper(session=session, limit=3).scrape()

    assert len(records) == 3
    assert len(session.calls) == 1


def test_scrape_sends_a_timeout_and_the_search_filter(session):
    """A request without a timeout can hang the whole pipeline."""
    NintendoScraper(session=session, limit=1).scrape()
    call = session.calls[0]

    assert call["timeout"] > 0
    assert call["params"]["fq"] == config.NINTENDO_SEARCH_FILTER
    assert call["params"]["sort"] == "popularity asc"


def test_scrape_skips_entries_without_an_id_or_title():
    """Regression: entries with no id used to end up with the literal id 'None'."""
    docs = [
        {"title": "Mario Kart World", "nsuid_txt": ["70010000096802"], "price_regular_f": 66.99},
        {"title": "Farm 2+"},
        {"title": "  ", "nsuid_txt": ["70010000000001"]},
    ]
    session = FakeSession({"searching": {"response": {"numFound": 3, "docs": docs}}})

    records = NintendoScraper(session=session).scrape()

    assert [record["name"] for record in records] == ["Mario Kart World"]
    assert records[0]["price"] == 66.99
    assert records[0]["url"] is None


def test_scrape_raises_on_network_error():
    session = FakeSession({"searching": requests.ConnectionError("boom")})

    with pytest.raises(ScrapeError, match="Failed to scrape Nintendo"):
        NintendoScraper(session=session).scrape()


def test_scrape_raises_when_the_index_is_empty():
    session = FakeSession({"searching": {"response": {"numFound": 0, "docs": []}}})

    with pytest.raises(ScrapeError, match="No Nintendo games found"):
        NintendoScraper(session=session).scrape()


def test_scrape_raises_on_error_status():
    session = FakeSession({})  # every URL answers 404

    with pytest.raises(ScrapeError, match="404"):
        NintendoScraper(session=session).scrape()
