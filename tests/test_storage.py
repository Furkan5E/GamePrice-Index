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


LEGACY_COLUMNS = "name, price, price_old, product_code, platform, url, badge, out_of_stock, source, scrape_timestamp"


def _legacy_db(tmp_path, rows) -> str:
    db_path = str(tmp_path / "old.db")
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE prices (name TEXT, price REAL, price_old REAL, product_code TEXT, platform TEXT, "
        "url TEXT, badge TEXT, out_of_stock INTEGER, source TEXT, scrape_timestamp TIMESTAMP)"
    )
    legacy.executemany(f"INSERT INTO prices ({LEGACY_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    legacy.commit()
    legacy.close()
    return db_path


def test_legacy_rows_are_migrated(tmp_path):
    """Databases written by early versions must open with their history intact."""
    mario = ("Mario Kart World", 66.99, None, "70010000096802", "Nintendo Switch 2", "u", None, None, "Nintendo")
    db_path = _legacy_db(
        tmp_path,
        [
            (*mario, "2026-08-21 10:00:00"),
            (*mario, "2026-08-21 18:30:00"),  # a second run on the same day
            (*mario, "2026-08-22 09:00:00"),
            ("No Code", 4.99, None, None, "Nintendo Switch", "u", None, None, "Nintendo", "2026-08-21 10:00:00"),
        ],
    )

    with storage.open_db(db_path) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        dates = [row["scrape_date"] for row in conn.execute("SELECT scrape_date FROM prices ORDER BY scrape_date")]

        assert storage.LEGACY_TABLE not in tables
        assert _count(conn, "games") == 1
        assert dates == ["2026-08-21", "2026-08-22"]
        assert storage.record_prices(conn, _frame(), DAY_ONE) == 2


def test_legacy_migration_repairs_swapped_sale_prices(tmp_path):
    db_path = _legacy_db(
        tmp_path,
        [
            (
                "Kero Kero Cowboy",
                8.99,
                7.64,
                "70010000126803.0",
                "Nintendo Switch",
                "u",
                None,
                None,
                "Nintendo",
                "2026-08-21 10:00:00",
            )
        ],
    )

    with storage.open_db(db_path) as conn:
        row = conn.execute("SELECT g.product_code, p.* FROM prices p JOIN games g ON g.id = p.game_id").fetchone()

        assert row["product_code"] == "70010000126803"
        assert (row["price"], row["price_old"]) == (7.64, 8.99)
        assert row["discount_amount"] == pytest.approx(1.35)
