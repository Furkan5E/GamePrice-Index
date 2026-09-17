import json

import pytest

from gameprice_index import config
from gameprice_index.processor import build_frame
from gameprice_index.scrapers import ScrapeError
from gameprice_index.scrapers.xbox import XboxScraper, pick_price
from helpers import FakeSession


@pytest.fixture
def session(load_fixture):
    """Serves page one, then page two when the continuation token from page one is sent back."""
    pages = [json.loads(load_fixture(f"xbox_browse_page{n}.json")) for n in (1, 2)]

    def browse(url, json=None, **kwargs):
        return pages[1] if json.get("EncodedCT") == "TOKEN-PAGE-2" else pages[0]

    return FakeSession({"emerald.xboxservices.com": browse})


def test_pick_price():
    product = {"specificPrices": {"purchaseable": [{"listPrice": 35.0, "msrp": 69.99}]}}

    assert pick_price(product) == (35.0, 69.99)
    assert pick_price({"specificPrices": {"purchaseable": []}}) == (None, None)
    assert pick_price({}) == (None, None)


def test_scrape_follows_the_continuation_token(session):
    records = XboxScraper(session=session).scrape()

    assert [record["name"] for record in records] == [
        "Gears of War: E-Day",
        "Grand Theft Auto VI: Ultimate Edition",
        "EA SPORTS™ Madden NFL 27",
        "Fortnite",
        "Grand Theft Auto V (Xbox One)",
    ]
    assert [call["json"].get("EncodedCT") for call in session.calls] == [None, "TOKEN-PAGE-2"]
    assert all(call["method"] == "POST" for call in session.calls)
    assert records[0] == {
        "source": "Xbox",
        "platform": "Xbox",
        "product_code": "9N4PT8HGCDHQ",
        "name": "Gears of War: E-Day",
        "price": 59.99,
        "price_old": 59.99,
        "badge": None,
        "out_of_stock": None,
        "url": "https://www.xbox.com/en-GB/games/store/_/9N4PT8HGCDHQ",
    }


def test_scrape_reads_sales_free_and_unpriced_games(session):
    df = build_frame(XboxScraper(session=session).scrape()).set_index("name")

    madden = df.loc["EA SPORTS™ Madden NFL 27"]
    assert (madden["price"], madden["price_old"], madden["discount_pct"]) == (35.0, 69.99, 50.0)
    assert df.loc["Fortnite", "price"] == 0.0
    assert df.loc["Grand Theft Auto V (Xbox One)", ["price", "price_old"]].isna().all()
    # msrp equal to the list price is not a discount
    assert df["discount_pct"].notna().sum() == 1


def test_request_carries_the_headers_the_service_requires(session):
    XboxScraper(session=session, limit=1).scrape()
    call = session.calls[0]

    assert call["params"] == {"locale": "en-GB"}
    assert call["headers"]["x-ms-api-version"] == "1.1"
    assert call["headers"]["Xbox-Market"] == "GB"
    assert call["headers"]["ms-cv"].endswith(".1")
    assert call["json"]["ChannelKeyToBeUsedInResponse"] == config.XBOX_CHANNEL_KEY
    assert call["timeout"] > 0


def test_scrape_stops_paging_at_the_limit(session):
    assert len(XboxScraper(session=session, limit=2).scrape()) == 2
    assert len(session.calls) == 1


def test_scrape_keeps_games_only(session):
    page = {
        "channels": {config.XBOX_CHANNEL_KEY: {"totalItems": 2}},
        "productSummaries": [
            {"productId": "A", "title": "A Game", "productKind": "Game"},
            {"productId": "B", "title": "Some Add-on", "productKind": "Durable"},
        ],
    }

    records = XboxScraper(session=FakeSession({"emerald": page})).scrape()

    assert [record["name"] for record in records] == ["A Game"]


def test_scrape_stops_at_the_page_cap(monkeypatch):
    """A service that keeps handing out tokens must not loop forever."""
    monkeypatch.setattr(config, "XBOX_MAX_PAGES", 3)
    endless = {
        "channels": {config.XBOX_CHANNEL_KEY: {"encodedCT": "AGAIN"}},
        "productSummaries": [{"productId": "A", "title": "A Game", "productKind": "Game"}],
    }
    session = FakeSession({"emerald": endless})

    XboxScraper(session=session).scrape()

    assert len(session.calls) == 3


def test_scrape_raises_when_nothing_is_returned():
    session = FakeSession({"emerald": {"channels": {}, "productSummaries": []}})

    with pytest.raises(ScrapeError, match="No Xbox games found"):
        XboxScraper(session=session).scrape()
