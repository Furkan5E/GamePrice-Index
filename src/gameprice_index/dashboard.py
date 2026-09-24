"""Streamlit dashboard over the price history.

Start it with `gameprice-index dashboard`, or directly with
`streamlit run src/gameprice_index/dashboard.py`. The database path comes from
the GAMEPRICE_DB environment variable and defaults to data/game_prices.db.
"""

import os
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from gameprice_index import config, storage
from gameprice_index.matching import cross_store_prices, store_comparison
from gameprice_index.visualiser import SOURCE_COLOURS, sources_in

DATABASE_ENV = "GAMEPRICE_DB"
CACHE_SECONDS = 300


def database_path() -> str:
    return os.environ.get(DATABASE_ENV) or os.path.join(config.DATA_DIR, config.DATABASE_NAME)


@st.cache_data(ttl=CACHE_SECONDS)
def load_latest(db_path: str) -> pd.DataFrame:
    """The most recent price of every game, in the shape of the pipeline's dataset."""
    with storage.open_db(db_path) as conn:
        latest = storage.latest_prices(conn)
    latest["discount_pct"] = (100 * latest["discount_amount"] / latest["price_old"]).round(1)
    return latest


@st.cache_data(ttl=CACHE_SECONDS)
def load_summary(db_path: str) -> pd.DataFrame:
    with storage.open_db(db_path) as conn:
        return storage.source_summary(conn)


@st.cache_data(ttl=CACHE_SECONDS)
def load_drops(db_path: str) -> pd.DataFrame:
    with storage.open_db(db_path) as conn:
        return storage.price_drops(conn)


@st.cache_data(ttl=CACHE_SECONDS)
def load_history(db_path: str, game_id: int) -> pd.DataFrame:
    with storage.open_db(db_path) as conn:
        return storage.game_history(conn, game_id)


def colour_scale(sources: list[str]) -> alt.Scale:
    """The same colour per storefront as the static plots."""
    return alt.Scale(domain=sources, range=[SOURCE_COLOURS.get(source, "#6250d6") for source in sources])


def money(column: str) -> Any:
    """A table column formatted as pounds."""
    return st.column_config.NumberColumn(column, format="£%.2f")


def render_overview(latest: pd.DataFrame, summary: pd.DataFrame) -> None:
    st.subheader("Storefronts")
    for column, row in zip(st.columns(max(len(summary), 1)), summary.to_dict("records"), strict=False):
        price = "n/a" if pd.isna(row["average_price"]) else f"£{row['average_price']:.2f}"
        column.metric(str(row["source"]), f"{row['games']:,} games", f"{row['on_sale']:,} on sale", delta_color="off")
        column.caption(f"Average price {price}")

    priced = latest.dropna(subset=["price"])
    ceiling = float(priced["price"].quantile(0.98)) if not priced.empty else 1.0
    sources = sources_in(priced)
    chart = (
        alt.Chart(priced[priced["price"] <= ceiling])
        .mark_bar(opacity=0.85)
        .encode(
            x=alt.X("price:Q", bin=alt.Bin(maxbins=30), title="Price (£)"),
            y=alt.Y("count():Q", title="Games"),
            color=alt.Color("source:N", scale=colour_scale(sources), legend=None),
            tooltip=[alt.Tooltip("source:N"), alt.Tooltip("count():Q", title="Games")],
        )
        .properties(height=140)
        .facet(row=alt.Row("source:N", title=None, sort=sources))
    )
    st.subheader("Price distribution")
    st.caption(f"Each storefront on its own row; the dearest 2% of games (over £{ceiling:,.0f}) are left out.")
    st.altair_chart(chart, use_container_width=True)


def render_deals(latest: pd.DataFrame) -> None:
    deals = latest.dropna(subset=["discount_pct"])
    sources = sources_in(deals)

    left, middle, right = st.columns([2, 2, 3])
    chosen = left.multiselect("Storefront", sources, default=sources, key="deal_sources")
    minimum = middle.slider("Minimum discount (%)", 0, 95, 50, step=5, key="deal_minimum")
    search = right.text_input("Name contains", key="deal_search")

    shown = deals[deals["source"].isin(chosen) & (deals["discount_pct"] >= minimum)]
    if search:
        shown = shown[shown["name"].str.contains(search, case=False, regex=False)]
    shown = shown.sort_values(["discount_pct", "name"], ascending=[False, True])

    st.caption(f"{len(shown):,} of {len(deals):,} games on sale")
    st.dataframe(
        shown[["name", "source", "platform", "price", "price_old", "discount_pct", "url"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "price": money("Now"),
            "price_old": money("Was"),
            "discount_pct": st.column_config.NumberColumn("Discount", format="%.0f%%"),
            "url": st.column_config.LinkColumn("Store page", display_text="open"),
        },
    )


def render_comparison(latest: pd.DataFrame) -> None:
    matched = cross_store_prices(latest)
    if matched.empty:
        st.info("No game is sold on more than one of the scraped storefronts yet.")
        return

    stores = [source for source in sources_in(latest) if source in matched.columns]
    comparison = store_comparison(matched, stores)
    comparison = comparison[comparison["shared_games"] >= 20]

    st.caption(
        f"{len(matched):,} games are sold on at least two storefronts. Regular prices are compared, "
        "so a sale on one store does not count as that store being cheaper."
    )
    chart = (
        alt.Chart(comparison)
        .mark_bar()
        .encode(
            x=alt.X("mean_difference_pct:Q", title="Average price difference against the other stores (%)"),
            y=alt.Y("source:N", title=None, sort=stores),
            color=alt.Color("source:N", scale=colour_scale(stores), legend=None),
            tooltip=[
                alt.Tooltip("source:N"),
                alt.Tooltip("mean_difference_pct:Q", title="Difference (%)"),
                alt.Tooltip("shared_games:Q", title="Shared games"),
                alt.Tooltip("cheapest_share_pct:Q", title="Cheapest or tied (%)"),
            ],
        )
        .properties(height=60 * max(len(comparison), 1))
    )
    st.altair_chart(chart, use_container_width=True)

    st.subheader("Biggest price gaps for the same game")
    st.dataframe(
        matched.drop(columns=["title_key"]).sort_values("spread", ascending=False).head(200),
        hide_index=True,
        use_container_width=True,
        column_config={**{store: money(store) for store in stores}, "spread": money("Gap")},
    )


def render_history(db_path: str, latest: pd.DataFrame, drops: pd.DataFrame) -> None:
    st.subheader("Latest price drops")
    if drops.empty:
        st.info("No price has fallen since the previous scrape. This fills in once there are two days of history.")
    else:
        st.dataframe(
            drops[["name", "source", "previous_price", "price", "drop_pct", "scrape_date"]].head(100),
            hide_index=True,
            use_container_width=True,
            column_config={
                "previous_price": money("Before"),
                "price": money("Now"),
                "drop_pct": st.column_config.NumberColumn("Drop", format="%.0f%%"),
            },
        )

    st.subheader("Price history of one game")
    search = st.text_input("Search for a game", key="history_search")
    if not search:
        return

    matches = latest[latest["name"].str.contains(search, case=False, regex=False)].head(50)
    if matches.empty:
        st.warning("No game matches that search.")
        return

    labels = {int(row["game_id"]): f"{row['name']} ({row['source']})" for row in matches.to_dict("records")}
    game_id = st.selectbox("Game", list(labels), format_func=lambda game: labels[game], key="history_game")
    history = load_history(db_path, int(game_id))
    priced = history.dropna(subset=["price"])
    if priced.empty:
        st.info("This game has never had a price recorded.")
        return

    low = priced.loc[priced["price"].idxmin()]
    left, right = st.columns(2)
    left.metric("Latest price", f"£{priced['price'].iloc[-1]:.2f}")
    right.metric("Lowest recorded", f"£{low['price']:.2f}", f"on {low['scrape_date']}", delta_color="off")
    st.line_chart(priced.set_index("scrape_date")["price"], y_label="Price (£)")


def main() -> None:
    st.set_page_config(page_title="GamePrice-Index", page_icon="🎮", layout="wide")
    st.title("GamePrice-Index")

    db_path = database_path()
    if not os.path.exists(db_path):
        st.error(f"No price history at `{db_path}`. Run `gameprice-index` first, or set {DATABASE_ENV}.")
        return

    latest = load_latest(db_path)
    if latest.empty:
        st.warning("The price history is empty. Run `gameprice-index` to record a first scrape.")
        return

    summary = load_summary(db_path)
    st.caption(f"{len(latest):,} games across {len(summary)} storefronts · last scrape {summary['last_scrape'].max()}")

    overview, deals, comparison, history = st.tabs(["Overview", "Deals", "Same game, different store", "History"])
    with overview:
        render_overview(latest, summary)
    with deals:
        render_deals(latest)
    with comparison:
        render_comparison(latest)
    with history:
        render_history(db_path, latest, load_drops(db_path))


if __name__ == "__main__":
    main()
