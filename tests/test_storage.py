import sqlite3
from datetime import date

import pandas as pd
import pytest

from gameprice_index import storage

DAY_ONE = date(2026, 9, 1)
DAY_TWO = date(2026, 9, 2)


def _frame(**overrides) -> pd.DataFrame:
    rows = [
        {
            "source": "Nintendo",
            "product_code": "70010000096802",
            "name": "Mario Kart World",
            "platform": "Nintendo Switch 2",
            "url": "https://example.test/mk",
            "price": 66.99,
            "price_old": float("nan"),
            "discount_amount": float("nan"),
            "badge": None,
            "out_of_stock": None,
        },
        {
            "source": "PlayStation",
            "product_code": "1000044444-GB",
            "name": "Astro Bot - PS5",
            "platform": "PS5",
            "url": "https://example.test/astro",
            "price": 39.99,
            "price_old": 59.99,
            "discount_amount": 20.0,
            "badge": "SALE",
            "out_of_stock": False,
        },
    ]
    df = pd.DataFrame(rows)
    for column, value in overrides.items():
        df[column] = value
    return df


@pytest.fixture
def conn(tmp_path):
    with storage.open_db(str(tmp_path / "prices.db")) as connection:
        yield connection


def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_open_db_creates_schema(conn):
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert {"games", "prices"} <= tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == storage.SCHEMA_VERSION


def test_record_prices_stores_games_and_prices(conn):
    assert storage.record_prices(conn, _frame(), DAY_ONE) == 2

    assert _count(conn, "games") == 2
    assert _count(conn, "prices") == 2

    astro = conn.execute(
        "SELECT p.* FROM prices p JOIN games g ON g.id = p.game_id WHERE g.product_code = '1000044444-GB'"
    ).fetchone()
    assert astro["price"] == 39.99
    assert astro["price_old"] == 59.99
    assert astro["badge"] == "SALE"
    assert astro["out_of_stock"] == 0
    assert astro["scrape_date"] == "2026-09-01"


def test_missing_values_are_stored_as_null(conn):
    storage.record_prices(conn, _frame(), DAY_ONE)

    mario = conn.execute(
        "SELECT p.* FROM prices p JOIN games g ON g.id = p.game_id WHERE g.name = 'Mario Kart World'"
    ).fetchone()
    assert mario["price_old"] is None
    assert mario["discount_amount"] is None
    assert mario["out_of_stock"] is None


def test_same_day_rerun_updates_instead_of_duplicating(conn):
    """Regression: every run used to append the whole dataset again."""
    storage.record_prices(conn, _frame(), DAY_ONE)
    storage.record_prices(conn, _frame(price=9.99), DAY_ONE)

    assert _count(conn, "games") == 2
    assert _count(conn, "prices") == 2
    assert {row["price"] for row in conn.execute("SELECT price FROM prices")} == {9.99}


def test_new_day_adds_history(conn):
    storage.record_prices(conn, _frame(), DAY_ONE)
    storage.record_prices(conn, _frame(), DAY_TWO)

    assert _count(conn, "games") == 2
    assert _count(conn, "prices") == 4

    game = conn.execute("SELECT first_seen, last_seen FROM games LIMIT 1").fetchone()
    assert (game["first_seen"], game["last_seen"]) == ("2026-09-01", "2026-09-02")


def test_same_code_on_two_storefronts_is_two_games(conn):
    df = _frame(product_code="SHARED-1")

    storage.record_prices(conn, df, DAY_ONE)

    assert _count(conn, "games") == 2


def test_rows_without_product_code_are_skipped(conn):
    df = _frame()
    df.loc[0, "product_code"] = None

    assert storage.record_prices(conn, df, DAY_ONE) == 1
    assert _count(conn, "games") == 1


def test_duplicate_price_row_is_rejected_by_the_schema(conn):
    """The primary key, not just the upsert, guarantees one row per game per day."""
    storage.record_prices(conn, _frame(), DAY_ONE)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO prices (game_id, scrape_date, scraped_at) VALUES (1, '2026-09-01', '2026-09-01T00:00:00')"
        )


def test_legacy_flat_table_is_set_aside(tmp_path):
    """Databases written by early versions must still open."""
    db_path = str(tmp_path / "old.db")
    legacy = sqlite3.connect(db_path)
    legacy.execute("CREATE TABLE prices (name TEXT, price REAL, source TEXT, scrape_timestamp TEXT)")
    legacy.execute("INSERT INTO prices VALUES ('Mario Kart World', 66.99, 'Nintendo', '2026-08-21 10:00:00')")
    legacy.commit()
    legacy.close()

    with storage.open_db(db_path) as conn:
        assert _count(conn, storage.LEGACY_TABLE) == 1
        assert storage.record_prices(conn, _frame(), DAY_ONE) == 2
