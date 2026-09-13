"""SQLite storage for the price history.

Two tables: `games` holds one row per product per storefront, and `prices`
holds at most one row per game per day. Re-running the pipeline on the same
day updates that day's row instead of adding a duplicate.
"""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime

import pandas as pd

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id           INTEGER PRIMARY KEY,
    source       TEXT NOT NULL,
    product_code TEXT NOT NULL,
    name         TEXT NOT NULL,
    platform     TEXT,
    url          TEXT,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    UNIQUE (source, product_code)
);

CREATE TABLE IF NOT EXISTS prices (
    game_id         INTEGER NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    scrape_date     TEXT NOT NULL,
    price           REAL,
    price_old       REAL,
    discount_amount REAL,
    badge           TEXT,
    out_of_stock    INTEGER,
    scraped_at      TEXT NOT NULL,
    PRIMARY KEY (game_id, scrape_date)
);

CREATE INDEX IF NOT EXISTS idx_prices_scrape_date ON prices (scrape_date);
"""

UPSERT_GAME = """
INSERT INTO games (source, product_code, name, platform, url, first_seen, last_seen)
VALUES (:source, :product_code, :name, :platform, :url, :scrape_date, :scrape_date)
ON CONFLICT (source, product_code) DO UPDATE SET
    name = excluded.name,
    platform = excluded.platform,
    url = excluded.url,
    first_seen = MIN(games.first_seen, excluded.first_seen),
    last_seen = MAX(games.last_seen, excluded.last_seen)
RETURNING id
"""

UPSERT_PRICE = """
INSERT INTO prices (game_id, scrape_date, price, price_old, discount_amount, badge, out_of_stock, scraped_at)
VALUES (:game_id, :scrape_date, :price, :price_old, :discount_amount, :badge, :out_of_stock, :scraped_at)
ON CONFLICT (game_id, scrape_date) DO UPDATE SET
    price = excluded.price,
    price_old = excluded.price_old,
    discount_amount = excluded.discount_amount,
    badge = excluded.badge,
    out_of_stock = excluded.out_of_stock,
    scraped_at = excluded.scraped_at
"""


LEGACY_TABLE = "prices_legacy"


def _set_aside_legacy_table(conn: sqlite3.Connection) -> None:
    """Renames the old flat `prices` table so the new schema can take its place.

    Early versions appended every scrape to one wide table with a
    `scrape_timestamp` column. Its rows are kept, just under another name.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(prices)")}
    if "scrape_timestamp" in columns:
        logger.warning(f"Found the old flat prices table; keeping its rows as {LEGACY_TABLE}.")
        conn.execute(f"ALTER TABLE prices RENAME TO {LEGACY_TABLE}")


def init_schema(conn: sqlite3.Connection) -> None:
    """Creates the tables if they are missing."""
    _set_aside_legacy_table(conn)
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


@contextmanager
def open_db(db_path: str) -> Iterator[sqlite3.Connection]:
    """Opens the database with the schema in place and closes it afterwards."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        init_schema(conn)
        yield conn
    finally:
        conn.close()


def _clean(value: object) -> object:
    """Turns pandas missing values into None so SQLite stores NULL."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


def _number(value: object) -> float | None:
    value = _clean(value)
    return None if value is None else float(value)  # type: ignore[arg-type]


def _flag(value: object) -> int | None:
    value = _clean(value)
    return None if value is None else int(bool(value))


def record_prices(conn: sqlite3.Connection, df: pd.DataFrame, scrape_date: date | None = None) -> int:
    """Upserts one price row per game for the given day and returns how many were written.

    Rows without a product code or a name cannot be tracked over time and are skipped.
    """
    day = (scrape_date or date.today()).isoformat()
    scraped_at = datetime.now(UTC).isoformat(timespec="seconds")

    written = 0
    skipped = 0
    with conn:  # one transaction: either the whole scrape is recorded or none of it
        for row in df.to_dict("records"):
            product_code = _clean(row.get("product_code"))
            name = _clean(row.get("name"))
            if not product_code or not name:
                skipped += 1
                continue

            game_id = conn.execute(
                UPSERT_GAME,
                {
                    "source": row["source"],
                    "product_code": str(product_code),
                    "name": name,
                    "platform": _clean(row.get("platform")),
                    "url": _clean(row.get("url")),
                    "scrape_date": day,
                },
            ).fetchone()["id"]

            conn.execute(
                UPSERT_PRICE,
                {
                    "game_id": game_id,
                    "scrape_date": day,
                    "price": _number(row.get("price")),
                    "price_old": _number(row.get("price_old")),
                    "discount_amount": _number(row.get("discount_amount")),
                    "badge": _clean(row.get("badge")),
                    "out_of_stock": _flag(row.get("out_of_stock")),
                    "scraped_at": scraped_at,
                },
            )
            written += 1

    if skipped:
        logger.warning(f"Skipped {skipped} rows without a product code or name.")
    logger.info(f"Recorded {written} prices for {day}.")
    return written
