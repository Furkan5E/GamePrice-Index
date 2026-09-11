"""End-to-end pipeline runs with the network replaced by saved pages."""

import sqlite3

import pandas as pd
import pytest

from gameprice_index import cli
from gameprice_index.scraper import parse_nintendo_listing, parse_nintendo_prices, parse_playstation_tiles


@pytest.fixture
def offline_scrapers(monkeypatch, load_fixture):
    """Makes every scraper answer from the saved fixtures and counts the calls."""
    calls = {"nintendo": 0, "playstation": 0}

    def nintendo_base(url):
        calls["nintendo"] += 1
        return parse_nintendo_listing(load_fixture("nintendo_listing_rendered.html"))

    def nintendo_prices(url):
        return parse_nintendo_prices(load_fixture("nintendo_listing_rendered.html"))

    def playstation(url):
        calls["playstation"] += 1
        return parse_playstation_tiles(load_fixture("playstation_direct_listing.html"))

    monkeypatch.setattr(cli, "scrape_nintendo_base", nintendo_base)
    monkeypatch.setattr(cli, "scrape_nintendo_prices", nintendo_prices)
    monkeypatch.setattr(cli, "scrape_playstation", playstation)
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
    assert len(df) == 9
    assert (data_dir / "processed_nintendo.csv").exists()
    assert (data_dir / "processed_playstation.csv").exists()
    assert _db_rows(data_dir / "game_prices.db") == 9

    wonder = df[df["name"].str.startswith("Super Mario Bros. Wonder")].iloc[0]
    assert wonder["product_code"] == "70010000115568"
    assert (df["discount_amount"].dropna() > 0).all()


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
