"""A small read-only HTTP API over the price history.

Run it with `gameprice-index serve`, or point any ASGI server at
`gameprice_index.api:app` (the database path then comes from GAMEPRICE_DB).
Interactive documentation is served at /docs.
"""

import os
import sqlite3
from collections.abc import Iterator
from typing import Annotated, Any

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from gameprice_index import __version__, config, storage

DATABASE_ENV = "GAMEPRICE_DB"
MAX_PAGE_SIZE = 200


class Game(BaseModel):
    game_id: int
    source: str
    product_code: str
    name: str
    platform: str | None = None
    url: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None
    scrape_date: str | None = None
    price: float | None = None
    price_old: float | None = None
    discount_amount: float | None = None
    badge: str | None = None
    out_of_stock: bool | None = None


class PricePoint(BaseModel):
    scrape_date: str
    price: float | None = None
    price_old: float | None = None
    discount_amount: float | None = None
    badge: str | None = None
    out_of_stock: bool | None = None


class GameHistory(BaseModel):
    game: Game
    lowest_price: float | None
    history: list[PricePoint]


class Deal(BaseModel):
    game_id: int
    source: str
    product_code: str
    name: str
    platform: str | None = None
    url: str | None = None
    price: float
    price_old: float
    discount_pct: float


class PriceDrop(BaseModel):
    source: str
    product_code: str
    name: str
    url: str | None = None
    previous_date: str
    previous_price: float
    scrape_date: str
    price: float
    drop_amount: float
    drop_pct: float


class SourceSummary(BaseModel):
    source: str
    games: int
    on_sale: int
    average_price: float | None = None
    last_scrape: str | None = None


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Converts a dataframe to JSON-ready dicts, with missing values as null rather than NaN."""
    rows = df.astype(object).where(df.notna(), None).to_dict("records")
    return [{str(column): value for column, value in row.items()} for row in rows]


def create_app(db_path: str | None = None) -> FastAPI:
    """Builds the API for one database file."""
    resolved_path = db_path or os.environ.get(DATABASE_ENV) or os.path.join(config.DATA_DIR, config.DATABASE_NAME)

    app = FastAPI(
        title="GamePrice-Index API",
        description="Current prices, deals and price history for video games across storefronts.",
        version=__version__,
    )

    def get_conn() -> Iterator[sqlite3.Connection]:
        # a connection per request: SQLite connections must not be shared between threads
        if not os.path.exists(resolved_path):
            raise HTTPException(status_code=503, detail="No price history yet; run the pipeline first.")
        with storage.open_db(resolved_path) as conn:
            yield conn

    Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
    PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Rows to return.")]

    @app.get("/health")
    def health() -> dict[str, Any]:
        """Reports whether the API can see a price history."""
        return {"status": "ok", "version": __version__, "database": os.path.exists(resolved_path)}

    @app.get("/sources", response_model=list[SourceSummary])
    def sources(conn: Conn) -> list[dict[str, Any]]:
        """Summarises each storefront: games tracked, games on sale and the average price."""
        return _records(storage.source_summary(conn))

    @app.get("/games", response_model=list[Game])
    def games(
        conn: Conn,
        source: Annotated[str | None, Query(description="Only this storefront, e.g. Steam.")] = None,
        q: Annotated[str | None, Query(min_length=2, description="Text the name must contain.")] = None,
        limit: PageSize = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict[str, Any]]:
        """Lists games with their latest price."""
        return _records(storage.find_games(conn, source=source, query=q, limit=limit, offset=offset))

    @app.get("/games/{game_id}", response_model=Game)
    def game(conn: Conn, game_id: int) -> dict[str, Any]:
        """Returns one game with its latest price."""
        found = _records(storage.get_game(conn, game_id))
        if not found:
            raise HTTPException(status_code=404, detail=f"No game with id {game_id}.")
        return found[0]

    @app.get("/games/{game_id}/history", response_model=GameHistory)
    def history(conn: Conn, game_id: int) -> dict[str, Any]:
        """Returns every recorded price of one game, oldest first."""
        found = _records(storage.get_game(conn, game_id))
        if not found:
            raise HTTPException(status_code=404, detail=f"No game with id {game_id}.")

        points = storage.game_history(conn, game_id)
        lowest = points["price"].min()
        return {
            "game": found[0],
            "lowest_price": None if pd.isna(lowest) else float(lowest),
            "history": _records(points),
        }

    @app.get("/deals", response_model=list[Deal])
    def deals(
        conn: Conn,
        source: Annotated[str | None, Query(description="Only this storefront.")] = None,
        min_discount: Annotated[float, Query(ge=0, le=100, description="Smallest discount in percent.")] = 0,
        limit: PageSize = 50,
    ) -> list[dict[str, Any]]:
        """Lists games on sale right now, deepest discount first."""
        found = storage.current_deals(conn)
        if source:
            found = found[found["source"] == source]
        found = found[found["discount_pct"] >= min_discount]
        return _records(found.head(limit))

    @app.get("/drops", response_model=list[PriceDrop])
    def drops(
        conn: Conn,
        min_drop: Annotated[float, Query(ge=0, description="Smallest price cut in pounds.")] = 0.01,
        limit: PageSize = 50,
    ) -> list[dict[str, Any]]:
        """Lists games whose latest price is below the one recorded before it."""
        return _records(storage.price_drops(conn, min_drop=min_drop).head(limit))

    return app


app = create_app()
