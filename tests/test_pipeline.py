"""End-to-end pipeline runs with the network replaced by saved responses."""

import json
import sqlite3

import pandas as pd
import pytest

from gameprice_index import cli
from gameprice_index.scrapers.nintendo import NintendoScraper
from gameprice_index.scrapers.playstation import PlayStationScraper, parse_playstation_tiles


@pytest.fixture
def offline_scrapers(monkeypatch, load_fixture):
    """Makes every scraper answer from the saved fixtures and counts the scrapes."""
    calls = {"nintendo": 0, "playstation": 0}

    def nintendo_catalogue(self):
        calls["nintendo"] += 1
        pages = [json.loads(load_fixture(f"nintendo_search_page{n}.json")) for n in (1, 2)]
        return [doc for page in pages for doc in page["response"]["docs"]]

    def playstation_records(self):
        calls["playstation"] += 1
        tiles = parse_playstation_tiles(load_fixture("playstation_direct_listing.html"))
        return [self.record(platform="PS5", **tile) for tile in tiles]

    monkeypatch.setattr(NintendoScraper, "fetch_catalogue", nintendo_catalogue)
    monkeypatch.setattr(PlayStationScraper, "fetch_records", playstation_records)
    return calls


def _db_rows(db_path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    finally:
        conn.close()


def test_live_run_writes_dataset_cache_and_database(tmp_path, offline_scrapers):
    assert cli.main(["--output-dir", str(tmp_path), "--no-plots"]) == 0

    data_dir = tmp_path / "data"
    df = pd.read_csv(data_dir / "data.csv", dtype={"product_code": "string"})

    assert sorted(df["source"].unique()) == ["Nintendo", "PlayStation"]
    assert len(df) == 10
    assert (data_dir / "processed_nintendo.csv").exists()
    assert (data_dir / "processed_playstation.csv").exists()
    assert _db_rows(data_dir / "game_prices.db") == 10

    hogwarts = df[df["name"] == "Hogwarts Legacy"].iloc[0]
    assert hogwarts["product_code"] == "70010000062277"
    assert (df["discount_amount"].dropna() > 0).all()
    assert df["discount_amount"].notna().sum() == 2


def test_cached_run_reproduces_the_live_run(tmp_path, offline_scrapers):
    """A --cached run must rebuild exactly the same dataset without scraping or logging history."""
    args = ["--output-dir", str(tmp_path), "--no-plots"]
    data_csv = tmp_path / "data" / "data.csv"
    db_path = tmp_path / "data" / "game_prices.db"

    assert cli.main(args) == 0
    live_csv = data_csv.read_text(encoding="utf-8")
    live_rows = _db_rows(db_path)

    assert cli.main([*args, "--cached"]) == 0

    assert data_csv.read_text(encoding="utf-8") == live_csv
    assert _db_rows(db_path) == live_rows
    assert offline_scrapers == {"nintendo": 1, "playstation": 1}


def test_failed_source_leaves_existing_cache_alone(tmp_path, offline_scrapers, monkeypatch):
    """Regression: one failing source used to overwrite the other sources' good cache."""
    args = ["--output-dir", str(tmp_path), "--no-plots"]
    assert cli.main(args) == 0
    before = (tmp_path / "data" / "processed_nintendo.csv").read_text(encoding="utf-8")

    monkeypatch.setattr(PlayStationScraper, "fetch_records", lambda self: [])

    assert cli.main(args) == 1
    assert (tmp_path / "data" / "processed_nintendo.csv").read_text(encoding="utf-8") == before
