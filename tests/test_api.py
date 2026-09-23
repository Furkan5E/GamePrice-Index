from datetime import date

import pytest
from fastapi.testclient import TestClient

from gameprice_index import storage
from gameprice_index.api import create_app
from gameprice_index.processor import build_frame


def _frame(astro_price: float, mario_price: float = 66.99, mario_old: float | None = None):
    return build_frame(
        [
            {
                "source": "Nintendo",
                "platform": "Nintendo Switch 2",
                "product_code": "70010000096802",
                "name": "Mario Kart World",
                "price": mario_price,
                "price_old": mario_old,
                "url": "https://example.test/mk",
            },
            {
                "source": "PlayStation Store",
                "platform": "PS5",
                "product_code": "EP9000",
                "name": "Astro Bot",
                "price": astro_price,
                "price_old": 59.99,
                "out_of_stock": False,
            },
            {"source": "Steam", "platform": "PC", "product_code": "1", "name": "100% Orange Juice", "price": None},
        ]
    )


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "prices.db")
    with storage.open_db(db_path) as conn:
        storage.record_prices(conn, _frame(39.99), date(2026, 9, 1))
        storage.record_prices(conn, _frame(29.99, mario_price=49.99, mario_old=66.99), date(2026, 9, 2))
    return TestClient(create_app(db_path))


def _id(client, name: str) -> int:
    return client.get("/games", params={"q": name}).json()[0]["game_id"]


def test_health(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["database"] is True


def test_games_lists_latest_prices(client):
    games = client.get("/games").json()

    assert [game["name"] for game in games] == ["100% Orange Juice", "Astro Bot", "Mario Kart World"]
    assert games[1]["price"] == 29.99
    assert games[1]["out_of_stock"] is False
    assert games[1]["scrape_date"] == "2026-09-02"


def test_missing_values_are_null_not_nan(client):
    """NaN is not valid JSON; unpriced games must come back with null."""
    unpriced = client.get("/games", params={"q": "orange"}).json()[0]

    assert unpriced["price"] is None
    assert unpriced["url"] is None


def test_games_filters_and_paginates(client):
    assert [g["name"] for g in client.get("/games", params={"source": "Steam"}).json()] == ["100% Orange Juice"]
    assert [g["name"] for g in client.get("/games", params={"q": "mario"}).json()] == ["Mario Kart World"]
    assert [g["name"] for g in client.get("/games", params={"limit": 1, "offset": 1}).json()] == ["Astro Bot"]
    assert client.get("/games", params={"q": "100%"}).json()[0]["name"] == "100% Orange Juice"


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 5000}, {"offset": -1}, {"q": "a"}])
def test_games_rejects_bad_parameters(client, params):
    assert client.get("/games", params=params).status_code == 422


def test_game_by_id(client):
    game = client.get(f"/games/{_id(client, 'astro')}").json()

    assert game["name"] == "Astro Bot"
    assert game["product_code"] == "EP9000"


def test_unknown_game_is_a_404(client):
    assert client.get("/games/9999").status_code == 404
    assert client.get("/games/9999/history").status_code == 404
    assert client.get("/games/not-a-number").status_code == 422


def test_history(client):
    body = client.get(f"/games/{_id(client, 'astro')}/history").json()

    assert body["game"]["name"] == "Astro Bot"
    assert [(point["scrape_date"], point["price"]) for point in body["history"]] == [
        ("2026-09-01", 39.99),
        ("2026-09-02", 29.99),
    ]
    assert body["lowest_price"] == 29.99


def test_history_of_a_game_that_was_never_priced(client):
    body = client.get(f"/games/{_id(client, 'orange')}/history").json()

    assert body["lowest_price"] is None
    assert len(body["history"]) == 2


def test_deals(client):
    deals = client.get("/deals").json()

    assert [(deal["name"], deal["discount_pct"]) for deal in deals] == [("Astro Bot", 50.0), ("Mario Kart World", 25.4)]
    assert [d["name"] for d in client.get("/deals", params={"min_discount": 40}).json()] == ["Astro Bot"]
    assert [d["name"] for d in client.get("/deals", params={"source": "Nintendo"}).json()] == ["Mario Kart World"]
    assert len(client.get("/deals", params={"limit": 1}).json()) == 1


def test_drops(client):
    drops = client.get("/drops").json()

    assert {drop["name"] for drop in drops} == {"Astro Bot", "Mario Kart World"}
    astro = next(drop for drop in drops if drop["name"] == "Astro Bot")
    assert (astro["previous_price"], astro["price"], astro["drop_amount"]) == (39.99, 29.99, 10.0)
    assert [d["name"] for d in client.get("/drops", params={"min_drop": 15}).json()] == ["Mario Kart World"]


def test_sources(client):
    summary = {row["source"]: row for row in client.get("/sources").json()}

    assert summary["Nintendo"]["games"] == 1
    assert summary["Nintendo"]["on_sale"] == 1
    assert summary["Steam"]["average_price"] is None
    assert summary["Steam"]["on_sale"] == 0
    assert summary["PlayStation Store"]["last_scrape"] == "2026-09-02"


def test_api_is_read_only(client):
    assert client.post("/games", json={}).status_code == 405
    assert client.delete(f"/games/{_id(client, 'astro')}").status_code == 405


def test_missing_database_is_reported_not_created(tmp_path):
    missing = tmp_path / "missing.db"
    client = TestClient(create_app(str(missing)))

    assert client.get("/health").json()["database"] is False
    assert client.get("/games").status_code == 503
    assert not missing.exists()


def test_openapi_schema_documents_every_endpoint(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert set(paths) == {
        "/health",
        "/sources",
        "/games",
        "/games/{game_id}",
        "/games/{game_id}/history",
        "/deals",
        "/drops",
    }
