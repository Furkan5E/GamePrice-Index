"""Price alerts for a personal watchlist.

A watchlist is a TOML file of games to keep an eye on:

    [[watch]]
    title = "Hogwarts Legacy"   # matched on any storefront, however the store spells it
    max_price = 20.00           # alert when it costs this or less

    [[watch]]
    title = "Hades II"          # no max_price: alert whenever it hits a new all-time low
    source = "Steam"            # optional: only this storefront

Each game and price is only reported once, so a sale that lasts a fortnight
does not send fourteen messages. Alerts are printed, and also posted to Discord
when a webhook URL is supplied through the DISCORD_WEBHOOK_URL environment variable.
"""

import logging
import sqlite3
import tomllib
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests

from gameprice_index import storage
from gameprice_index.http_client import fetch
from gameprice_index.matching import normalise_title

logger = logging.getLogger(__name__)


class WatchlistError(ValueError):
    """Raised when the watchlist file cannot be used."""


@dataclass(frozen=True)
class Watch:
    title: str
    max_price: float | None = None
    source: str | None = None

    @property
    def key(self) -> str:
        return normalise_title(self.title)


@dataclass(frozen=True)
class Alert:
    game_id: int
    source: str
    name: str
    price: float
    reason: str
    url: str | None = None
    price_old: float | None = None

    def message(self) -> str:
        was = f" (was £{self.price_old:.2f})" if self.price_old else ""
        link = f"\n{self.url}" if self.url else ""
        return f"**{self.name}** on {self.source}: £{self.price:.2f}{was} - {self.reason}{link}"


def load_watchlist(path: str) -> list[Watch]:
    """Reads and checks a watchlist file."""
    try:
        with open(path, "rb") as file:
            entries = tomllib.load(file).get("watch", [])
    except FileNotFoundError as e:
        raise WatchlistError(f"No watchlist at {path}.") from e
    except tomllib.TOMLDecodeError as e:
        raise WatchlistError(f"Watchlist {path} is not valid TOML: {e}") from e

    watches = []
    for number, entry in enumerate(entries, start=1):
        title = str(entry.get("title", "")).strip()
        if not normalise_title(title):
            raise WatchlistError(f"Watchlist entry {number} needs a title.")

        max_price = entry.get("max_price")
        if max_price is not None and (isinstance(max_price, bool) or not isinstance(max_price, (int, float))):
            raise WatchlistError(f"Watchlist entry {number} ({title}): max_price must be a number.")
        if max_price is not None and max_price < 0:
            raise WatchlistError(f"Watchlist entry {number} ({title}): max_price cannot be negative.")

        watches.append(Watch(title=title, max_price=max_price, source=entry.get("source")))
    return watches


def _previous_low(conn: sqlite3.Connection, game_id: int, latest_date: str) -> float | None:
    """The lowest price recorded for a game before its latest scrape."""
    row = conn.execute(
        "SELECT MIN(price) FROM prices WHERE game_id = ? AND scrape_date < ? AND price IS NOT NULL",
        (game_id, latest_date),
    ).fetchone()
    return row[0]


def find_alerts(conn: sqlite3.Connection, watchlist: list[Watch]) -> list[Alert]:
    """Compares the latest prices with the watchlist and returns what is worth reporting."""
    latest = storage.latest_prices(conn).dropna(subset=["price"])
    latest["title_key"] = latest["name"].map(normalise_title)

    alerts = []
    for watch in watchlist:
        games = latest[latest["title_key"] == watch.key]
        if watch.source:
            games = games[games["source"].str.lower() == watch.source.lower()]
        if games.empty:
            logger.info(f"Watchlist: no priced game matches '{watch.title}'.")

        for game in games.to_dict("records"):
            price = float(game["price"])
            if watch.max_price is not None:
                if price > watch.max_price:
                    continue
                reason = f"at or under your £{watch.max_price:.2f} target"
            else:
                previous_low = _previous_low(conn, int(game["game_id"]), str(game["scrape_date"]))
                # with no earlier price there is nothing to be lower than
                if previous_low is None or price >= previous_low:
                    continue
                reason = f"new all-time low (previous £{previous_low:.2f})"

            alerts.append(
                Alert(
                    game_id=int(game["game_id"]),
                    source=str(game["source"]),
                    name=str(game["name"]),
                    price=price,
                    reason=reason,
                    url=game["url"] if isinstance(game["url"], str) else None,
                    price_old=float(game["price_old"]) if pd.notna(game["price_old"]) else None,
                )
            )
    return alerts


def unsent(conn: sqlite3.Connection, alerts: list[Alert]) -> list[Alert]:
    """Drops alerts that were already sent for the same game at the same price."""
    fresh = []
    for alert in alerts:
        seen = conn.execute(
            "SELECT 1 FROM alerts_sent WHERE game_id = ? AND price = ?", (alert.game_id, alert.price)
        ).fetchone()
        if not seen:
            fresh.append(alert)
    return fresh


def mark_sent(conn: sqlite3.Connection, alerts: list[Alert], sent_on: date | None = None) -> None:
    """Remembers which alerts went out so they are not repeated."""
    day = (sent_on or date.today()).isoformat()
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO alerts_sent (game_id, price, sent_date) VALUES (?, ?, ?)",
            [(alert.game_id, alert.price, day) for alert in alerts],
        )


# --- Delivery ---

DISCORD_MESSAGE_LIMIT = 2000  # characters; Discord rejects anything longer


def chunk_messages(alerts: list[Alert], limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """Packs alert messages into as few posts as the length limit allows."""
    chunks: list[str] = []
    current = ""
    for alert in alerts:
        message = alert.message()[:limit]
        if current and len(current) + len(message) + 2 > limit:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{message}" if current else message
    if current:
        chunks.append(current)
    return chunks


def send_discord(alerts: list[Alert], webhook_url: str, session: requests.Session | None = None) -> int:
    """Posts the alerts to a Discord webhook and returns how many posts were made."""
    chunks = chunk_messages(alerts)
    for chunk in chunks:
        # mentions are switched off so a game title can never ping a channel
        fetch(webhook_url, session=session, method="POST", json={"content": chunk, "allowed_mentions": {"parse": []}})
    return len(chunks)


def run_alerts(
    db_path: str,
    watchlist_path: str,
    webhook_url: str | None = None,
    dry_run: bool = False,
    session: requests.Session | None = None,
) -> list[Alert]:
    """Finds new alerts, delivers them and records them as sent; a dry run only reports them."""
    watchlist = load_watchlist(watchlist_path)

    with storage.open_db(db_path) as conn:
        fresh = unsent(conn, find_alerts(conn, watchlist))
        if not fresh or dry_run:
            return fresh

        if webhook_url:
            posts = send_discord(fresh, webhook_url, session=session)
            logger.info(f"Sent {len(fresh)} alerts to Discord in {posts} posts.")
        # only remembered once delivery has worked, so a failed post is retried on the next run
        mark_sent(conn, fresh)
    return fresh
