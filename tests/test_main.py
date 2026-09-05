import pandas as pd
import pytest
from src.main import load_cache, write_cache
from src.scraper import ScrapeError

def test_write_cache_refuses_empty_dataset(tmp_path):
    """Regression: a failed scrape used to replace good cached data with an empty file."""
    path = tmp_path / "raw_nintendo.csv"
    path.write_text("name,price\nMario Kart World,66.99\n", encoding="utf-8")

    with pytest.raises(ScrapeError):
        write_cache(pd.DataFrame(), str(path))

    assert "Mario Kart World" in path.read_text(encoding="utf-8")

def test_load_cache_reports_empty_file(tmp_path):
    """Regression: an empty cached file used to crash --cached with EmptyDataError."""
    path = tmp_path / "raw_nintendo.csv"
    path.write_text("\n", encoding="utf-8")

    with pytest.raises(ScrapeError, match="is empty"):
        load_cache(str(path))

def test_load_cache_keeps_ids_as_strings(tmp_path):
    """A missing id must not turn the whole column into floats like 70010000096802.0."""
    path = tmp_path / "raw_nintendo.csv"
    path.write_text(
        "name,nsuid,product_code\nMario Kart World,70010000096802,70010000096802\nNo Id,,\n",
        encoding="utf-8",
    )

    df = load_cache(str(path))

    assert df["nsuid"][0] == "70010000096802"
    assert df["product_code"][0] == "70010000096802"
    assert pd.isna(df["nsuid"][1])
