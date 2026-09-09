import pandas as pd
import pytest

from gameprice_index import cli, config
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


def test_load_cache_reports_missing_file(tmp_path):
    with pytest.raises(ScrapeError, match="No cached file"):
        load_cache(str(tmp_path / "missing.csv"))


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

    def failing_pipeline(**kwargs):
        raise ScrapeError("No Nintendo games found")

    monkeypatch.setattr(cli, "run_pipeline", failing_pipeline)

    assert cli.main([]) == 1


def test_main_defaults(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "run_pipeline", lambda **kwargs: seen.update(kwargs))

    assert cli.main([]) == 0
    assert seen == {"use_cache": False, "sources": ("nintendo", "playstation"), "make_plots": True}


def test_main_passes_options(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "run_pipeline", lambda **kwargs: seen.update(kwargs))

    assert cli.main(["--cached", "--source", "nintendo", "--no-plots"]) == 0
    assert seen == {"use_cache": True, "sources": ("nintendo",), "make_plots": False}


def test_main_rejects_unknown_source():
    with pytest.raises(SystemExit):
        cli.main(["--source", "sega"])


NINTENDO_CACHE = (
    "name,platform,url,nsuid,price,price_old,badge,date_range,product_code,out_of_stock,source\n"
    "Mario Kart World,Nintendo Switch 2,https://example.test/mk,70010000096802,66.99,,,,70010000096802,,Nintendo\n"
    "Kero Kero Cowboy,Nintendo Switch,https://example.test/kk,70010000126803,7.64,8.99,,,70010000126803,,Nintendo\n"
)


def test_cached_single_source_run_without_plots(tmp_path, monkeypatch):
    """--cached --source nintendo --no-plots only needs the Nintendo cache and writes no plots."""
    data_dir = tmp_path / "data"
    plots_dir = tmp_path / "plots"
    data_dir.mkdir()
    (data_dir / "processed_nintendo.csv").write_text(NINTENDO_CACHE, encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(config, "PLOTS_DIR", str(plots_dir))

    assert cli.main(["--cached", "--source", "nintendo", "--no-plots"]) == 0

    df = pd.read_csv(data_dir / "data.csv")
    assert df["source"].unique().tolist() == ["Nintendo"]
    assert df["discount_amount"].dropna().tolist() == [pytest.approx(1.35)]
    assert not plots_dir.exists()
    assert not (data_dir / "game_prices.db").exists()
