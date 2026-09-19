"""End-to-end pipeline runs with the network replaced by saved responses."""

import json
import sqlite3

import pandas as pd
import pytest

from gameprice_index import cli
from gameprice_index.scrapers import SCRAPERS, Scraper
from helpers import FakeSession


@pytest.fixture
def offline(monkeypatch, load_fixture):
    """Gives every scraper a session that answers from the saved fixtures and records all requests."""
    search = [json.loads(load_fixture(f"nintendo_search_page{n}.json")) for n in (1, 2)]

    def nintendo_search(url, params=None, **kwargs):
        docs = [doc for page in search for doc in page["response"]["docs"]]
        return {"response": {"numFound": len(docs), "docs": docs[params["start"] :]}}

    session = FakeSession(
        {
            "searching.nintendo-europe.com": nintendo_search,
            "api.ec.nintendo.com": json.loads(load_fixture("nintendo_prices.json")),
            "api.direct.playstation.com": json.loads(load_fixture("playstation_direct_products.json")),
        }
    )

    original_init = Scraper.__init__

    def init_with_fake_session(self, session_=None, limit=None, **kwargs):
        original_init(self, session=session, limit=limit)

    monkeypatch.setattr(Scraper, "__init__", init_with_fake_session)
    return session


SOURCES = ["nintendo", "playstation-direct"]
SOURCE_ARGS = [arg for source in SOURCES for arg in ("--source", source)]


def _db_rows(db_path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    finally:
        conn.close()


def test_fixture_sources_are_registered():
    assert set(SOURCES) <= set(SCRAPERS)


def test_live_run_writes_dataset_cache_and_database(tmp_path, offline):
    assert cli.main([*SOURCE_ARGS, "--output-dir", str(tmp_path), "--no-plots"]) == 0

    data_dir = tmp_path / "data"
    df = pd.read_csv(data_dir / "data.csv", dtype={"product_code": "string"})

    assert sorted(df["source"].unique()) == ["Nintendo", "PlayStation Direct"]
    assert len(df) == 10
    assert (data_dir / "processed_nintendo.csv").exists()
    assert (data_dir / "processed_playstation-direct.csv").exists()
    assert _db_rows(data_dir / "game_prices.db") == 10

    hogwarts = df[df["name"] == "Hogwarts Legacy"].iloc[0]
    assert hogwarts["product_code"] == "70010000062277"
    assert (df["discount_amount"].dropna() > 0).all()
    assert df["discount_amount"].notna().sum() == 1
    assert df[df["name"] == "Minecraft"]["badge"].tolist() == ["PRE-ORDER"]


def test_run_writes_the_cross_store_table(tmp_path, offline):
    """The table is written even when no game is shared, so later steps can rely on the file."""
    assert cli.main([*SOURCE_ARGS, "--output-dir", str(tmp_path), "--no-plots"]) == 0

    matched = pd.read_csv(tmp_path / "data" / "cross_store_prices.csv")
    assert "cheapest_store" in matched.columns
    assert matched.empty  # the Nintendo and PlayStation Direct fixtures have no game in common


def test_cached_run_reproduces_the_live_run(tmp_path, offline):
    """A --cached run must rebuild exactly the same dataset without scraping or logging history."""
    args = [*SOURCE_ARGS, "--output-dir", str(tmp_path), "--no-plots"]
    data_csv = tmp_path / "data" / "data.csv"
    db_path = tmp_path / "data" / "game_prices.db"

    assert cli.main(args) == 0
    live_csv = data_csv.read_text(encoding="utf-8")
    live_rows = _db_rows(db_path)
    requests_made = len(offline.calls)

    assert cli.main([*args, "--cached"]) == 0

    assert data_csv.read_text(encoding="utf-8") == live_csv
    assert _db_rows(db_path) == live_rows
    assert len(offline.calls) == requests_made


def test_failed_source_leaves_existing_cache_alone(tmp_path, offline):
    """Regression: one failing source used to overwrite the other sources' good cache."""
    args = [*SOURCE_ARGS, "--output-dir", str(tmp_path), "--no-plots"]
    assert cli.main(args) == 0
    before = (tmp_path / "data" / "processed_nintendo.csv").read_text(encoding="utf-8")

    offline.routes["api.direct.playstation.com"] = {"products": []}

    assert cli.main(args) == 1
    assert (tmp_path / "data" / "processed_nintendo.csv").read_text(encoding="utf-8") == before


def test_limit_caps_every_source(tmp_path, offline):
    assert cli.main([*SOURCE_ARGS, "--output-dir", str(tmp_path), "--no-plots", "--limit", "2"]) == 0

    df = pd.read_csv(tmp_path / "data" / "data.csv")
    assert df["source"].value_counts().to_dict() == {"Nintendo": 2, "PlayStation Direct": 2}


def test_invalid_data_stops_the_run_before_anything_is_written(tmp_path, offline):
    """A source that still parses but returns nonsense must not reach the cache, the CSV or the history."""
    broken = json.loads(json.dumps(offline.routes["api.direct.playstation.com"]))
    broken["products"][0]["price"]["value"] = -69.99
    offline.routes["api.direct.playstation.com"] = broken

    assert cli.main([*SOURCE_ARGS, "--output-dir", str(tmp_path), "--no-plots"]) == cli.EXIT_INVALID_DATA
    assert list((tmp_path / "data").iterdir()) == []
