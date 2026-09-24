"""Runs the dashboard headlessly against a small database."""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from gameprice_index import dashboard, storage
from gameprice_index.processor import build_frame

APP_PATH = dashboard.__file__


def _frame(steam_price: float):
    records = []
    for source, platform in (("Nintendo", "Nintendo Switch"), ("Steam", "PC")):
        for n in range(1, 31):
            base = 10.0 + n
            on_sale = n % 3 == 0
            records.append(
                {
                    "source": source,
                    "platform": platform,
                    "product_code": f"{source}-{n}",
                    "name": f"Shared Game {n}",
                    "price": steam_price if (source, n) == ("Steam", 1) else (base / 2 if on_sale else base),
                    "price_old": base if on_sale else None,
                    "url": f"https://example.test/{source}/{n}",
                }
            )
    return build_frame(records)


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_path = str(tmp_path / "prices.db")
    with storage.open_db(db_path) as conn:
        storage.record_prices(conn, _frame(11.0), date(2026, 9, 1))
        storage.record_prices(conn, _frame(5.5), date(2026, 9, 2))
    monkeypatch.setenv(dashboard.DATABASE_ENV, db_path)
    return AppTest.from_file(APP_PATH, default_timeout=30)


def test_dashboard_renders_every_tab(app):
    app.run()

    assert not app.exception
    assert app.title[0].value == "GamePrice-Index"
    assert [tab.label for tab in app.tabs] == ["Overview", "Deals", "Same game, different store", "History"]
    assert "60 games across 2 storefronts" in app.caption[0].value
    assert {metric.label for metric in app.metric} >= {"Nintendo", "Steam"}


def test_deal_filters_narrow_the_table(app):
    app.run()
    everything = len(app.dataframe[0].value)

    app.multiselect(key="deal_sources").set_value(["Steam"]).run()
    steam_only = app.dataframe[0].value

    assert not app.exception
    assert 0 < len(steam_only) < everything
    assert set(steam_only["source"]) == {"Steam"}

    app.text_input(key="deal_search").set_value("Game 30").run()
    assert app.dataframe[0].value["name"].tolist() == ["Shared Game 30"]


def test_history_search_shows_the_price_record(app):
    app.run()
    app.text_input(key="history_search").set_value("Shared Game 1").run()

    assert not app.exception
    labels = {metric.label: metric.value for metric in app.metric}
    assert labels["Latest price"] == "£11.00"  # the Nintendo copy is listed first

    steam_copy = next(option for option in app.selectbox(key="history_game").options if "Steam" in option)
    app.selectbox(key="history_game").select(steam_copy).run()
    labels = {metric.label: metric.value for metric in app.metric}
    assert labels["Latest price"] == "£5.50"
    assert labels["Lowest recorded"] == "£5.50"


def test_dashboard_without_a_database(tmp_path, monkeypatch):
    monkeypatch.setenv(dashboard.DATABASE_ENV, str(tmp_path / "missing.db"))

    app = AppTest.from_file(APP_PATH, default_timeout=30).run()

    assert not app.exception
    assert "No price history" in app.error[0].value
    assert not (tmp_path / "missing.db").exists()
