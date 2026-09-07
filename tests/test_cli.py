import pandas as pd
import pytest
from gameprice_index import cli
from gameprice_index.cli import load_cache, write_cache
from gameprice_index.scraper import ScrapeError

def test_write_cache_refuses_empty_dataset(tmp_path):
    """Regression: a failed scrape used to replace good cached data with an empty file."""
    path = tmp_path / "processed_nintendo.csv"
    path.write_text("name,price\nMario Kart World,66.99\n", encoding="utf-8")

    with pytest.raises(ScrapeError):
        write_cache(pd.DataFrame(), str(path))

    assert "Mario Kart World" in path.read_text(encoding="utf-8")

def test_load_cache_reports_empty_file(tmp_path):
    """Regression: an empty cached file used to crash --cached with EmptyDataError."""
    path = tmp_path / "processed_nintendo.csv"
    path.write_text("\n", encoding="utf-8")

    with pytest.raises(ScrapeError, match="is empty"):
        load_cache(str(path))

def test_load_cache_keeps_ids_as_strings(tmp_path):
    """A missing id must not turn the whole column into floats like 70010000096802.0."""
    path = tmp_path / "processed_nintendo.csv"
    path.write_text(
        "name,nsuid,product_code\nMario Kart World,70010000096802,70010000096802\nNo Id,,\n",
        encoding="utf-8",
    )

    df = load_cache(str(path))

    assert df["nsuid"][0] == "70010000096802"
    assert df["product_code"][0] == "70010000096802"
    assert pd.isna(df["nsuid"][1])

def test_main_returns_error_code_when_scrape_fails(monkeypatch):
    """A failed source must surface as a non-zero exit code for cron and CI."""
    def failing_pipeline(use_cache=False):
        raise ScrapeError("No Nintendo games found")

    monkeypatch.setattr(cli, "run_pipeline", failing_pipeline)

    assert cli.main([]) == 1

def test_main_passes_cached_flag(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "run_pipeline", lambda use_cache=False: seen.update(use_cache=use_cache))

    assert cli.main(["--cached"]) == 0
    assert seen == {"use_cache": True}
