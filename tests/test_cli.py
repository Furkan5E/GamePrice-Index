import pandas as pd
import pytest

from gameprice_index import cli
from gameprice_index.cli import load_cache, write_cache
from gameprice_index.scrapers import ScrapeError


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
    path.write_text("name,product_code\nMario Kart World,70010000096802\nNo Id,\n", encoding="utf-8")

    df = load_cache(str(path))

    assert df["product_code"][0] == "70010000096802"
    assert pd.isna(df["product_code"][1])


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
    assert seen == {
        "use_cache": False,
        "sources": cli.SOURCES,
        "make_plots": True,
        "output_dir": ".",
        "db_path": None,
    }


def test_main_passes_options(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "run_pipeline", lambda **kwargs: seen.update(kwargs))

    args = ["--cached", "--source", "nintendo", "--no-plots", "--output-dir", "out", "--db", "prices.db"]

    assert cli.main(args) == 0
    assert seen == {
        "use_cache": True,
        "sources": ("nintendo",),
        "make_plots": False,
        "output_dir": "out",
        "db_path": "prices.db",
    }


def test_main_rejects_unknown_source():
    with pytest.raises(SystemExit):
        cli.main(["--source", "sega"])


NINTENDO_CACHE = (
    "source,platform,product_code,name,price,price_old,discount_amount,discount_pct,badge,out_of_stock,url\n"
    "Nintendo,Nintendo Switch 2,70010000096802,Mario Kart World,66.99,,,,,,https://example.test/mk\n"
    "Nintendo,Nintendo Switch,70010000126803,Kero Kero Cowboy,7.64,8.99,1.35,15.0,,,https://example.test/kk\n"
)


def _seed_nintendo_cache(output_dir):
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "processed_nintendo.csv").write_text(NINTENDO_CACHE, encoding="utf-8")
    return data_dir


def test_cached_single_source_run_without_plots(tmp_path):
    """--cached --source nintendo --no-plots only needs the Nintendo cache and writes no plots."""
    data_dir = _seed_nintendo_cache(tmp_path)

    assert cli.main(["--cached", "--source", "nintendo", "--no-plots", "--output-dir", str(tmp_path)]) == 0

    df = pd.read_csv(data_dir / "data.csv")
    assert df["source"].unique().tolist() == ["Nintendo"]
    assert df["discount_amount"].dropna().tolist() == [pytest.approx(1.35)]
    assert not (tmp_path / "plots").exists()
    assert not (data_dir / "game_prices.db").exists()


def test_cached_run_writes_plots_under_output_dir(tmp_path):
    _seed_nintendo_cache(tmp_path)

    assert cli.main(["--cached", "--source", "nintendo", "--output-dir", str(tmp_path)]) == 0

    plots = sorted(p.name for p in (tmp_path / "plots").iterdir())
    assert plots == ["platform_distribution.png", "price_analysis.png", "price_vs_discount.png"]
