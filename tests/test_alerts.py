from datetime import date

import pytest

from gameprice_index import alerts, storage
from gameprice_index.alerts import Watch, WatchlistError, find_alerts, load_watchlist
from gameprice_index.processor import build_frame

DAY_ONE = date(2026, 9, 1)
DAY_TWO = date(2026, 9, 2)
DAY_THREE = date(2026, 9, 3)


def _frame(hogwarts_steam: float, hades: float = 24.99):
    def row(source, code, name, price, price_old=None):
        return {
            "source": source,
            "product_code": code,
            "name": name,
            "price": price,
            "price_old": price_old,
            "url": f"https://example.test/{code}",
        }

    return build_frame(
        [
            row("Steam", "990080", "Hogwarts Legacy", hogwarts_steam, 49.99 if hogwarts_steam < 49.99 else None),
            row("PlayStation Store", "EP1018", "Hogwarts Legacy PS5", 59.99),
            row("Steam", "1145350", "Hades II", hades),
        ]
    )


@pytest.fixture
def conn(tmp_path):
    with storage.open_db(str(tmp_path / "prices.db")) as connection:
        storage.record_prices(connection, _frame(49.99), DAY_ONE)
        storage.record_prices(connection, _frame(12.49, hades=19.99), DAY_TWO)
        yield connection


def _write(tmp_path, text: str) -> str:
    path = tmp_path / "watchlist.toml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_load_watchlist(tmp_path):
    path = _write(
        tmp_path,
        '[[watch]]\ntitle = "Hogwarts Legacy"\nmax_price = 20\n\n[[watch]]\ntitle = "Hades II"\nsource = "Steam"\n',
    )

    assert load_watchlist(path) == [
        Watch(title="Hogwarts Legacy", max_price=20),
        Watch(title="Hades II", source="Steam"),
    ]


def test_load_watchlist_with_no_entries(tmp_path):
    assert load_watchlist(_write(tmp_path, "# nothing yet\n")) == []


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[[watch]]\nmax_price = 20\n", "needs a title"),
        ('[[watch]]\ntitle = "™"\n', "needs a title"),
        ('[[watch]]\ntitle = "Hades"\nmax_price = "cheap"\n', "must be a number"),
        ('[[watch]]\ntitle = "Hades"\nmax_price = -1\n', "cannot be negative"),
        ("[[watch]\n", "not valid TOML"),
    ],
)
def test_load_watchlist_rejects_bad_entries(tmp_path, text, message):
    with pytest.raises(WatchlistError, match=message):
        load_watchlist(_write(tmp_path, text))


def test_load_watchlist_missing_file(tmp_path):
    with pytest.raises(WatchlistError, match="No watchlist"):
        load_watchlist(str(tmp_path / "nope.toml"))


def test_target_price_alert_matches_any_store_spelling(conn):
    """ "Hogwarts Legacy PS5" is the same game, but only the Steam copy is under the target."""
    found = find_alerts(conn, [Watch(title="hogwarts legacy", max_price=20)])

    assert [(alert.source, alert.price) for alert in found] == [("Steam", 12.49)]
    assert found[0].reason == "at or under your £20.00 target"
    assert found[0].price_old == 49.99


def test_target_price_is_inclusive(conn):
    assert len(find_alerts(conn, [Watch(title="Hogwarts Legacy", max_price=12.49)])) == 1
    assert find_alerts(conn, [Watch(title="Hogwarts Legacy", max_price=12.48)]) == []


def test_new_low_alert(conn):
    found = find_alerts(conn, [Watch(title="Hades II")])

    assert [(alert.name, alert.price) for alert in found] == [("Hades II", 19.99)]
    assert found[0].reason == "new all-time low (previous £24.99)"


def test_no_new_low_alert_when_the_price_only_matches_the_low(conn):
    storage.record_prices(conn, _frame(12.49, hades=19.99), DAY_THREE)

    assert find_alerts(conn, [Watch(title="Hades II")]) == []


def test_no_new_low_alert_on_the_first_scrape(tmp_path):
    """With a single day of history every price would otherwise count as a record low."""
    with storage.open_db(str(tmp_path / "fresh.db")) as fresh:
        storage.record_prices(fresh, _frame(12.49), DAY_ONE)

        assert find_alerts(fresh, [Watch(title="Hogwarts Legacy")]) == []


def test_source_filter(conn):
    watch = Watch(title="Hogwarts Legacy", max_price=100, source="playstation store")

    assert [alert.source for alert in find_alerts(conn, [watch])] == ["PlayStation Store"]


def test_unknown_title_gives_no_alerts(conn):
    assert find_alerts(conn, [Watch(title="Half-Life 3", max_price=100)]) == []


def test_alert_message(conn):
    alert = find_alerts(conn, [Watch(title="Hogwarts Legacy", max_price=20)])[0]

    assert alert.message() == (
        "**Hogwarts Legacy** on Steam: £12.49 (was £49.99) - at or under your £20.00 target\n"
        "https://example.test/990080"
    )


def test_alerts_are_only_sent_once_per_price(conn):
    """A sale that lasts a fortnight must not produce fourteen identical messages."""
    watchlist = [Watch(title="Hogwarts Legacy", max_price=20)]
    first = alerts.unsent(conn, find_alerts(conn, watchlist))
    alerts.mark_sent(conn, first, DAY_TWO)

    assert len(first) == 1
    assert alerts.unsent(conn, find_alerts(conn, watchlist)) == []

    # a further cut is news again
    storage.record_prices(conn, _frame(9.99), DAY_THREE)
    again = alerts.unsent(conn, find_alerts(conn, watchlist))
    assert [alert.price for alert in again] == [9.99]
