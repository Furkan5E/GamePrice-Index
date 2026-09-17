import json

import pytest

from gameprice_index import config
from gameprice_index.processor import build_frame
from gameprice_index.scrapers import ScrapeError
from gameprice_index.scrapers.steam import SteamScraper, parse_search_rows
from helpers import FakeSession


@pytest.fixture
def payload(load_fixture):
    return json.loads(load_fixture("steam_search.json"))


def _row(app_id: str, title: str, price: str = "999") -> str:
    return (
        f'<a class="search_result_row" href="https://store.steampowered.com/app/{app_id}/x/?snr=1" '
        f'data-ds-appid="{app_id}"><span class="title">{title}</span>'
        f'<div class="search_price_discount_combined" data-price-final="{price}"></div></a>'
    )


def test_parse_search_rows(payload):
    games = parse_search_rows(payload["results_html"])

    assert [game["name"] for game in games] == ["Planet Zoo 2", "AION 2", "EA SPORTS FC™ 27", "ARC Raiders"]
    assert games[0] == {
        "product_code": "3219030",
        "name": "Planet Zoo 2",
        "price": 39.99,
        "price_old": None,
        "url": "https://store.steampowered.com/app/3219030/Planet_Zoo_2/",
    }


def test_parse_search_rows_reads_sales_and_free_games(payload):
    df = build_frame([{"source": "Steam", **game} for game in parse_search_rows(payload["results_html"])])
    arc = df[df["name"] == "ARC Raiders"].iloc[0]

    assert (arc["price"], arc["price_old"], arc["discount_pct"]) == (17.49, 34.99, 50.0)
    assert 0.0 in df["price"].tolist()


def test_parse_search_rows_skips_bundles():
    """Bundles list several app ids (or none) and are not a single game."""
    html = (
        _row("730", "Counter-Strike 2")
        + '<a class="search_result_row" data-ds-appid="10,20,30"><span class="title">Valve Complete Pack</span></a>'
        + '<a class="search_result_row" data-ds-bundleid="232"><span class="title">Some Bundle</span></a>'
    )

    assert [game["name"] for game in parse_search_rows(html)] == ["Counter-Strike 2"]


def test_parse_search_rows_without_a_price_block():
    html = '<a class="search_result_row" data-ds-appid="1"><span class="title">Unreleased</span></a>'

    game = parse_search_rows(html)[0]

    assert game["price"] is None
    assert game["url"] is None


def test_scrape_builds_records(payload):
    session = FakeSession({"store.steampowered.com": payload})

    records = SteamScraper(session=session).scrape()
    call = session.calls[0]

    assert len(records) == 4
    assert records[0]["source"] == "Steam"
    assert records[0]["platform"] == "PC"
    assert call["params"]["cc"] == "gb"
    assert call["params"]["filter"] == "topsellers"
    assert call["timeout"] > 0


def test_scrape_pages_and_removes_repeats(monkeypatch):
    """Rankings move between requests, so a game can appear on two pages."""
    monkeypatch.setattr(config, "STEAM_PAGE_SIZE", 2)
    pages = {
        0: _row("1", "One") + _row("2", "Two"),
        2: _row("2", "Two") + _row("3", "Three"),
        4: _row("4", "Four"),
    }

    def search(url, params=None, **kwargs):
        return {"success": 1, "results_html": pages[params["start"]], "total_count": 5}

    session = FakeSession({"store.steampowered.com": search})

    records = SteamScraper(session=session).scrape()

    assert [record["name"] for record in records] == ["One", "Two", "Three", "Four"]
    assert [call["params"]["start"] for call in session.calls] == [0, 2, 4]


def test_scrape_stops_paging_at_the_limit(monkeypatch):
    monkeypatch.setattr(config, "STEAM_PAGE_SIZE", 2)

    def search(url, params=None, **kwargs):
        start = params["start"]
        return {"results_html": _row(str(start), "A") + _row(str(start + 1), "B"), "total_count": 1000}

    session = FakeSession({"store.steampowered.com": search})

    assert len(SteamScraper(session=session, limit=3).scrape()) == 3
    assert len(session.calls) == 2


def test_scrape_raises_when_nothing_is_returned():
    session = FakeSession({"store.steampowered.com": {"success": 1, "results_html": "", "total_count": 0}})

    with pytest.raises(ScrapeError, match="No Steam games found"):
        SteamScraper(session=session).scrape()
