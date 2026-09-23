"""SQLite storage for the price history.

`games` holds one row per product per storefront and `prices` at most one row
per game per day, so re-running the pipeline on the same day updates that
day's row instead of adding a duplicate. `alerts_sent` remembers which price
alerts have gone out.
"""

import logging
import sqlite3
from collections.abc import Iterator, Mapping
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

CREATE TABLE IF NOT EXISTS alerts_sent (
    game_id   INTEGER NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    price     REAL NOT NULL,
    sent_date TEXT NOT NULL,
    PRIMARY KEY (game_id, price)
);
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
    """Creates the tables if they are missing and brings old data across."""
    _set_aside_legacy_table(conn)
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    migrate_legacy(conn)


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


def migrate_legacy(conn: sqlite3.Connection) -> int:
    """Moves rows from the old flat table into the new schema and returns how many were kept.

    The old table logged every run, including cached ones, so a day can hold
    many copies of a game; only the last scrape of each day survives.
    """
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (LEGACY_TABLE,)).fetchone()
    if not exists:
        return 0

    legacy = pd.read_sql_query(f"SELECT * FROM {LEGACY_TABLE}", conn)
    migrated = 0
    if not legacy.empty:
        legacy["scrape_timestamp"] = pd.to_datetime(legacy["scrape_timestamp"], errors="coerce")
        legacy = legacy.dropna(subset=["scrape_timestamp", "product_code"])
        # cached runs wrote numeric ids as floats, e.g. "70010000096802.0"
        legacy["product_code"] = legacy["product_code"].astype(str).str.replace(r"\.0$", "", regex=True)
        legacy["scrape_date"] = legacy["scrape_timestamp"].dt.date

        # old Nintendo rows stored the sale price and the original price the wrong way round
        prices = legacy[["price", "price_old"]].apply(pd.to_numeric, errors="coerce")
        swapped = prices["price_old"] < prices["price"]
        legacy["price"] = prices["price"].where(~swapped, prices["price_old"])
        legacy["price_old"] = prices["price_old"].where(~swapped, prices["price"])
        legacy["discount_amount"] = legacy["price_old"] - legacy["price"]

        legacy = legacy.sort_values("scrape_timestamp").drop_duplicates(
            subset=["source", "product_code", "scrape_date"], keep="last"
        )
        for day, rows in legacy.groupby("scrape_date"):
            migrated += record_prices(conn, rows, scrape_date=day)  # type: ignore[arg-type]

    conn.execute(f"DROP TABLE {LEGACY_TABLE}")
    conn.commit()
    logger.info(f"Migrated {migrated} rows from the old prices table.")
    return migrated


# --- Reading the history ---

LATEST_PRICES = """
WITH ranked AS (
    SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.game_id ORDER BY p.scrape_date DESC) AS recency
    FROM prices p
)
SELECT g.id AS game_id, g.source, g.product_code, g.name, g.platform, g.url,
       r.scrape_date, r.price, r.price_old, r.discount_amount, r.badge, r.out_of_stock
FROM ranked r
JOIN games g ON g.id = r.game_id
WHERE r.recency = 1
ORDER BY g.source, g.name
"""

PRICE_HISTORY = """
SELECT g.source, g.product_code, g.name, p.scrape_date, p.price, p.price_old, p.discount_amount
FROM prices p
JOIN games g ON g.id = p.game_id
WHERE g.product_code = :product_code AND (:source IS NULL OR g.source = :source)
ORDER BY g.source, p.scrape_date
"""

PRICE_DROPS = """
WITH ranked AS (
    SELECT p.game_id, p.scrape_date, p.price,
           LAG(p.price) OVER (PARTITION BY p.game_id ORDER BY p.scrape_date) AS previous_price,
           LAG(p.scrape_date) OVER (PARTITION BY p.game_id ORDER BY p.scrape_date) AS previous_date,
           ROW_NUMBER() OVER (PARTITION BY p.game_id ORDER BY p.scrape_date DESC) AS recency
    FROM prices p
    WHERE p.price IS NOT NULL
)
SELECT g.source, g.product_code, g.name, g.platform, g.url,
       r.previous_date, r.previous_price, r.scrape_date, r.price,
       ROUND(r.previous_price - r.price, 2) AS drop_amount,
       ROUND(100.0 * (r.previous_price - r.price) / r.previous_price, 1) AS drop_pct
FROM ranked r
JOIN games g ON g.id = r.game_id
WHERE r.recency = 1 AND r.previous_price > r.price AND (r.previous_price - r.price) >= :min_drop
ORDER BY drop_pct DESC, g.name
"""

LOWEST_PRICES = """
WITH ranked AS (
    SELECT p.game_id, p.scrape_date, p.price,
           ROW_NUMBER() OVER (PARTITION BY p.game_id ORDER BY p.price, p.scrape_date) AS cheapest
    FROM prices p
    WHERE p.price IS NOT NULL
)
SELECT g.source, g.product_code, g.name, r.price AS lowest_price, r.scrape_date AS lowest_date
FROM ranked r
JOIN games g ON g.id = r.game_id
WHERE r.cheapest = 1
ORDER BY g.source, g.name
"""


def _query(conn: sqlite3.Connection, sql: str, params: Mapping[str, object] | None = None) -> pd.DataFrame:
    """Runs a SELECT and returns the result as a dataframe, keeping the column names when it is empty."""
    cursor = conn.execute(sql, params or {})
    columns = [column[0] for column in cursor.description]
    return pd.DataFrame([tuple(row) for row in cursor.fetchall()], columns=columns)


def latest_prices(conn: sqlite3.Connection) -> pd.DataFrame:
    """Returns the most recent price recorded for every game."""
    return _query(conn, LATEST_PRICES)


def price_history(conn: sqlite3.Connection, product_code: str, source: str | None = None) -> pd.DataFrame:
    """Returns every recorded price for one product, oldest first."""
    return _query(conn, PRICE_HISTORY, {"product_code": product_code, "source": source})


def price_drops(conn: sqlite3.Connection, min_drop: float = 0.01) -> pd.DataFrame:
    """Returns games whose latest price is below the one recorded before it, biggest cut first."""
    return _query(conn, PRICE_DROPS, {"min_drop": min_drop})


def lowest_prices(conn: sqlite3.Connection) -> pd.DataFrame:
    """Returns the lowest price ever recorded for every game and the first day it was seen."""
    return _query(conn, LOWEST_PRICES)


def current_deals(conn: sqlite3.Connection, limit: int | None = None) -> pd.DataFrame:
    """Returns games that are on sale right now, deepest discount first."""
    latest = latest_prices(conn)
    deals = latest[latest["price_old"].notna() & (latest["price_old"] > latest["price"])].copy()
    deals["discount_pct"] = (100 * (deals["price_old"] - deals["price"]) / deals["price_old"]).round(1)
    deals = deals.sort_values(["discount_pct", "name"], ascending=[False, True]).reset_index(drop=True)
    return deals.head(limit) if limit else deals


# --- Lookups used by the API and the dashboard ---

FIND_GAMES = """
WITH ranked AS (
    SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.game_id ORDER BY p.scrape_date DESC) AS recency
    FROM prices p
)
SELECT g.id AS game_id, g.source, g.product_code, g.name, g.platform, g.url, g.first_seen, g.last_seen,
       r.scrape_date, r.price, r.price_old, r.discount_amount, r.badge, r.out_of_stock
FROM games g
LEFT JOIN ranked r ON r.game_id = g.id AND r.recency = 1
WHERE (:source IS NULL OR g.source = :source)
  AND (:pattern IS NULL OR g.name LIKE :pattern ESCAPE '\\')
  AND (:game_id IS NULL OR g.id = :game_id)
ORDER BY g.name, g.source
LIMIT :limit OFFSET :offset
"""

GAME_HISTORY = """
SELECT scrape_date, price, price_old, discount_amount, badge, out_of_stock
FROM prices
WHERE game_id = :game_id
ORDER BY scrape_date
"""

SOURCE_SUMMARY = """
WITH ranked AS (
    SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.game_id ORDER BY p.scrape_date DESC) AS recency
    FROM prices p
)
SELECT g.source,
       COUNT(*) AS games,
       COALESCE(SUM(r.price_old > r.price), 0) AS on_sale,
       ROUND(AVG(r.price), 2) AS average_price,
       MAX(r.scrape_date) AS last_scrape
FROM games g
JOIN ranked r ON r.game_id = g.id AND r.recency = 1
GROUP BY g.source
ORDER BY g.source
"""


def _like_pattern(text: str) -> str:
    """Wraps a search term for LIKE, escaping the characters LIKE treats as wildcards."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def find_games(
    conn: sqlite3.Connection,
    source: str | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> pd.DataFrame:
    """Lists games with their latest price, optionally filtered by storefront and a name fragment."""
    params = {
        "source": source,
        "pattern": _like_pattern(query) if query else None,
        "game_id": None,
        "limit": limit,
        "offset": offset,
    }
    return _query(conn, FIND_GAMES, params)


def get_game(conn: sqlite3.Connection, game_id: int) -> pd.DataFrame:
    """Returns one game with its latest price, or an empty dataframe if the id is unknown."""
    params = {"source": None, "pattern": None, "game_id": game_id, "limit": 1, "offset": 0}
    return _query(conn, FIND_GAMES, params)


def game_history(conn: sqlite3.Connection, game_id: int) -> pd.DataFrame:
    """Returns every recorded price of one game, oldest first."""
    return _query(conn, GAME_HISTORY, {"game_id": game_id})


def source_summary(conn: sqlite3.Connection) -> pd.DataFrame:
    """Returns the number of games, games on sale and average price per storefront."""
    return _query(conn, SOURCE_SUMMARY)
