import json

import pandas as pd
import pytest

from gameprice_index import config
from gameprice_index.processor import build_frame
from gameprice_index.scrapers import ScrapeError
from gameprice_index.scrapers.playstation_store import PlayStationStoreScraper, parse_money
from helpers import FakeSession


@pytest.fixture
def session(load_fixture):
    """Serves the two saved pages of the category grid according to the requested offset."""
    pages = [json.loads(load_fixture(f"playstation_store_page{n}.json")) for n in (1, 2)]

    def grid(url, params=None, **kwargs):
        offset = json.loads(params["variables"])["pageArgs"]["offset"]
        return pages[0] if offset == 0 else pages[1]

    return FakeSession({"web.np.playstation.com": grid})


@pytest.mark.parametrize(
    ("text", "expected"),
    [("£49.99", 49.99), ("£1,299.00", 1299.0), ("Free", 0.0), ("", None), (None, None), ("Unavailable", None)],
)
def test_parse_money(text, expected):
    assert parse_money(text) == expected


def test_parse_money_trusts_the_free_flag():
    assert parse_money("£0.00", is_free=True) == 0.0


def test_scrape_pages_through_the_catalogue(session):
    records = PlayStationStoreScraper(session=session).scrape()

    assert [record["name"] for record in records] == [
        "STAR WARS: Galactic Racer™",
        "Clive Barker's Hellraiser: Revival",
        "Marvel’s Wolverine",
        "007 First Light",
        "NBA 2K27",
    ]
    offsets = [json.loads(call["params"]["variables"])["pageArgs"]["offset"] for call in session.calls]
    assert offsets == [0, 3]
    assert records[0]["source"] == "PlayStation Store"
    assert records[0]["platform"] == "PS5"
    assert records[0]["url"].startswith("https://store.playstation.com/en-gb/product/")
    assert records[0]["url"].endswith(records[0]["product_code"])


def test_scrape_reads_sale_prices(session):
    records = PlayStationStoreScraper(session=session).scrape()
    df = build_frame(records).set_index("name")

    assert df.loc["007 First Light", ["price", "price_old", "discount_pct"]].tolist() == [41.99, 59.99, 30.0]
    # the store sends the regular price twice when nothing is on sale
    assert pd.isna(df.loc["Marvel’s Wolverine", "price_old"])
    assert df.loc["Marvel’s Wolverine", "price"] == 69.99


def test_request_identifies_the_persisted_query(session):
    PlayStationStoreScraper(session=session, limit=1).scrape()
    call = session.calls[0]
    variables = json.loads(call["params"]["variables"])
    extensions = json.loads(call["params"]["extensions"])

    assert call["params"]["operationName"] == "categoryGridRetrieve"
    assert variables["id"] == config.PLAYSTATION_STORE_CATEGORY_ID
    assert variables["filterBy"] == ["storeDisplayClassification:FULL_GAME"]
    assert extensions["persistedQuery"]["sha256Hash"] == config.PLAYSTATION_STORE_QUERY_HASH
    assert call["headers"]["x-psn-store-locale-override"] == "en-GB"
    assert call["headers"]["content-type"] == "application/json"
    assert call["timeout"] > 0


def test_scrape_stops_paging_at_the_limit(session):
    assert len(PlayStationStoreScraper(session=session, limit=2).scrape()) == 2
    assert len(session.calls) == 1


def _product(**price):
    base = {"basePrice": "£59.99", "discountedPrice": "£59.99", "isFree": False, "isTiedToSubscription": False}
    return {"id": "EP0001-PPSA00001_00-GAME", "name": "Game", "platforms": ["PS4", "PS5"], "price": {**base, **price}}


def test_parse_product_free_game():
    record = PlayStationStoreScraper().parse_product(_product(basePrice="Free", discountedPrice="Free", isFree=True))

    assert record["price"] == 0.0
    assert record["platform"] == "PS4/PS5"


def test_parse_product_ignores_subscriber_only_discounts():
    record = PlayStationStoreScraper().parse_product(_product(discountedPrice="£39.99", isTiedToSubscription=True))

    assert record["price"] == 59.99


def test_parse_product_marks_preorders():
    product = {**_product(), "skus": [{"type": "PREORDER"}]}

    assert PlayStationStoreScraper().parse_product(product)["badge"] == "PRE-ORDER"


def test_scrape_reports_a_rejected_query():
    """If Sony retires the persisted query the failure must say so, not look like an empty store."""
    session = FakeSession({"web.np.playstation.com": {"errors": [{"message": "PersistedQueryNotFound"}]}})

    with pytest.raises(ScrapeError, match="PersistedQueryNotFound"):
        PlayStationStoreScraper(session=session).scrape()
