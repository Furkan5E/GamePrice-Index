import json

import pytest

from gameprice_index import config
from gameprice_index.scrapers import ScrapeError
from gameprice_index.scrapers.playstation_direct import PlayStationDirectScraper
from helpers import FakeSession


@pytest.fixture
def payload(load_fixture):
    return json.loads(load_fixture("playstation_direct_products.json"))


def test_scrape_reads_the_catalogue(payload):
    session = FakeSession({"api.direct.playstation.com": payload})

    records = PlayStationDirectScraper(session=session).scrape()

    assert [record["product_code"] for record in records] == [
        "1000057436-GB",
        "1000049375-GB",
        "1000048721-GB",
        "1000039370-GB",
    ]
    assert records[0]["source"] == "PlayStation Direct"
    assert records[0]["platform"] == "PS5"
    assert records[0]["price"] == 69.99
    assert records[0]["price_old"] is None
    assert records[0]["out_of_stock"] is False
    assert records[0]["url"] == "https://direct.playstation.com/en-gb/buy-games/marvels-wolverine-ps5"
    assert records[1]["badge"] == "EXCLUSIVE"
    assert len(session.calls) == 1


def test_scrape_asks_for_json_with_a_timeout(payload):
    session = FakeSession({"api.direct.playstation.com": payload})

    PlayStationDirectScraper(session=session).scrape()
    call = session.calls[0]

    assert call["timeout"] > 0
    assert call["headers"] == {"Accept": "application/json"}
    assert call["params"]["currentPage"] == 0


def test_scrape_walks_every_page(payload):
    """Regression: only the last page of a multi-page listing used to be collected."""
    products = payload["products"]

    def paged(url, params=None, **kwargs):
        page = params["currentPage"]
        return {"products": products[page * 2 : page * 2 + 2], "pagination": {"totalPages": 2}}

    session = FakeSession({"api.direct.playstation.com": paged})

    records = PlayStationDirectScraper(session=session).scrape()

    assert len(records) == 4
    assert [call["params"]["currentPage"] for call in session.calls] == [0, 1]


def test_scrape_stops_paging_at_the_limit(payload):
    products = payload["products"]

    def paged(url, params=None, **kwargs):
        page = params["currentPage"]
        return {"products": products[page * 2 : page * 2 + 2], "pagination": {"totalPages": 2}}

    session = FakeSession({"api.direct.playstation.com": paged})

    assert len(PlayStationDirectScraper(session=session, limit=2).scrape()) == 2
    assert len(session.calls) == 1


def test_scrape_stops_at_the_page_cap(monkeypatch):
    """A service that always claims another page must not loop forever."""
    monkeypatch.setattr(config, "PLAYSTATION_DIRECT_MAX_PAGES", 3)
    endless = {"products": [{"code": "X", "name": "Loop"}], "pagination": {"totalPages": 999}}
    session = FakeSession({"api.direct.playstation.com": endless})

    PlayStationDirectScraper(session=session).scrape()

    assert len(session.calls) == 3


def test_parse_product_flags_stock_and_preorders():
    scraper = PlayStationDirectScraper()

    sold_out = scraper.parse_product({"code": "A", "name": "A", "stock": {"stockLevelStatus": "outOfStock"}})
    preorder = scraper.parse_product({"code": "B", "name": "B", "preOrderProduct": True})

    assert sold_out["out_of_stock"] is True
    assert preorder["badge"] == "PRE-ORDER"
    assert preorder["out_of_stock"] is None
    assert preorder["url"] is None


def test_scrape_raises_when_the_catalogue_is_empty():
    session = FakeSession({"api.direct.playstation.com": {"products": [], "pagination": {"totalPages": 0}}})

    with pytest.raises(ScrapeError, match="No PlayStation Direct games found"):
        PlayStationDirectScraper(session=session).scrape()
