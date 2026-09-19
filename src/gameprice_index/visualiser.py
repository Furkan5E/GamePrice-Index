"""Static plots comparing prices and discounts across storefronts."""

import logging
import os
from typing import Any

import matplotlib

matplotlib.use("Agg")  # render to files; no display is needed

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes

logger = logging.getLogger(__name__)

# one fixed colour per storefront, so a source looks the same in every plot and every run
SOURCE_COLOURS = {
    "Nintendo": "#2a78d6",
    "PlayStation Store": "#eb6834",
    "PlayStation Direct": "#1baf7a",
    "PlayStation": "#1baf7a",
    "Steam": "#eda100",
    "Xbox": "#e87ba4",
}
FALLBACK_COLOUR = "#6250d6"

SURFACE = "#fcfcfb"
INK = "#1f1f1e"
MUTED = "#6b6a63"
GRID = "#e4e3dd"

PRICE_CEILING_QUANTILE = 0.98  # collector's editions would otherwise flatten every chart
MIN_GAMES_FOR_DISTRIBUTION = 20  # a handful of games is not a distribution worth drawing


def colour_for(source: str) -> str:
    return SOURCE_COLOURS.get(source, FALLBACK_COLOUR)


def sources_in(df: pd.DataFrame) -> list[str]:
    """Sources present in the data, in the fixed colour order first."""
    present = set(df["source"].dropna().unique())
    known = [source for source in SOURCE_COLOURS if source in present]
    return known + sorted(present - set(known))


def _style(ax: Axes, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, fontsize=13, fontweight="bold", color=INK, loc="left", pad=12)
    ax.set_xlabel(xlabel, fontsize=11, color=MUTED)
    ax.set_ylabel(ylabel, fontsize=11, color=MUTED)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, length=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


def _legend(ax: Axes, **kwargs: Any) -> None:
    if ax.get_legend_handles_labels()[0]:
        ax.legend(frameon=False, labelcolor=INK, fontsize=10, **kwargs)


def _save(fig: plt.Figure, output_dir: str, filename: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    logger.info(f"Saved plot to {output_path}")
    return output_path


def plot_platform_distribution(df: pd.DataFrame, output_dir: str = "plots") -> str:
    """Bar chart of how many games each platform contributes, coloured by storefront."""
    counts = df.groupby(["source", "platform"]).size().reset_index(name="games").sort_values("games")
    # two storefronts can sell for the same platform, so the row label names both
    counts["label"] = counts["source"] + " · " + counts["platform"].fillna("unknown")

    fig, ax = plt.subplots(figsize=(9, max(3.5, 0.5 * len(counts) + 1.5)))
    labelled = set()
    for _, row in counts.iterrows():
        label = row["source"] if row["source"] not in labelled else None
        labelled.add(row["source"])
        bar = ax.barh(row["label"], row["games"], color=colour_for(row["source"]), height=0.6, label=label)
        ax.bar_label(bar, padding=4, color=INK, fontsize=10)

    _style(ax, "Games per platform", "Number of games", "")
    ax.grid(axis="y", visible=False)
    ax.margins(x=0.1)
    _legend(ax, loc="lower right")
    return _save(fig, output_dir, "platform_distribution.png")


def plot_price_analysis(df: pd.DataFrame, output_dir: str = "plots") -> str:
    """Two views of how prices are spread per storefront: by percentile and as a distribution."""
    priced = df.dropna(subset=["price"])
    sizes = priced["source"].value_counts()
    too_small = sorted(sizes[sizes < MIN_GAMES_FOR_DISTRIBUTION].index)
    if len(too_small) < len(sizes):
        priced = priced[~priced["source"].isin(too_small)]
    fig, (ax_rank, ax_hist) = plt.subplots(1, 2, figsize=(14, 5.5))

    ceiling = float(priced["price"].quantile(PRICE_CEILING_QUANTILE)) if not priced.empty else 1.0
    ceiling = max(ceiling, 1.0)
    # one set of bin edges for every source, otherwise the bars are not comparable
    bins = np.linspace(0, ceiling, 26)

    for source in sources_in(priced):
        prices = priced.loc[priced["source"] == source, "price"].sort_values().to_numpy()
        colour = colour_for(source)
        label = f"{source} ({len(prices):,})"

        # percentiles put catalogues of very different sizes on the same x axis
        percentiles = np.linspace(0, 100, len(prices)) if len(prices) > 1 else np.array([50.0])
        ax_rank.plot(percentiles, prices, color=colour, linewidth=2, label=label)

        share = np.histogram(np.clip(prices, 0, ceiling), bins=bins)[0] / len(prices) * 100
        ax_hist.stairs(share, bins, color=colour, linewidth=2, label=label)

    _style(
        ax_rank, "Price at each percentile of the catalogue", "Percentile of games (cheapest to dearest)", "Price (£)"
    )
    ax_rank.set_ylim(0, ceiling * 1.05)
    _legend(ax_rank, loc="upper left")

    _style(ax_hist, "Share of games in each price band", "Price (£)", "Share of the storefront's games (%)")
    _legend(ax_hist, loc="upper right")
    top_share = 100 - PRICE_CEILING_QUANTILE * 100
    note = f"Prices above £{ceiling:,.0f} (the top {top_share:.0f}%) are off the scale or counted in the last band."
    if too_small and len(too_small) < len(sizes):
        note += f" Not shown (under {MIN_GAMES_FOR_DISTRIBUTION} games): {', '.join(too_small)}."
    fig.text(
        0.99,
        0.01,
        note,
        ha="right",
        fontsize=9,
        color=MUTED,
    )
    return _save(fig, output_dir, "price_analysis.png")


def plot_price_vs_discount(df: pd.DataFrame, output_dir: str = "plots") -> str:
    """Scatter of regular price against discount depth for every game currently on sale."""
    deals = df.dropna(subset=["price_old", "discount_pct"])
    fig, ax = plt.subplots(figsize=(9, 5.5))

    for source in sources_in(deals):
        rows = deals[deals["source"] == source]
        ax.scatter(
            rows["price_old"],
            rows["discount_pct"],
            color=colour_for(source),
            label=f"{source} ({len(rows):,})",
            alpha=0.6,
            edgecolors=SURFACE,
            linewidths=0.6,
            s=36,
        )

    _style(ax, "Discount depth of on-sale games", "Regular price (£)", "Discount (%)")
    ax.set_ylim(0, 100)
    if not deals.empty:
        ax.set_xlim(0, float(deals["price_old"].quantile(PRICE_CEILING_QUANTILE)) * 1.05)
    else:
        ax.text(0.5, 0.5, "No games on sale", transform=ax.transAxes, ha="center", color=MUTED)
    # hundreds of points fill the whole plot area, so the legend sits above it
    _legend(ax, loc="lower right", bbox_to_anchor=(1, 1), ncol=5, columnspacing=1.2, handletextpad=0.3)
    return _save(fig, output_dir, "price_vs_discount.png")


def plot_cross_store_prices(comparison: pd.DataFrame, output_dir: str = "plots") -> str:
    """Bar chart of how each storefront prices the games it shares with other stores.

    `comparison` is the table from `matching.store_comparison`: the same games,
    regular prices, so the stores are compared like for like.
    """
    # an average over a handful of shared games says nothing about a store
    enough = comparison[comparison["shared_games"] >= MIN_GAMES_FOR_DISTRIBUTION]
    comparison = enough if not enough.empty else comparison

    fig, ax = plt.subplots(figsize=(9, max(3.0, 0.7 * len(comparison) + 1.8)))

    for _, row in comparison.iloc[::-1].iterrows():
        bar = ax.barh(row["source"], row["mean_difference_pct"], color=colour_for(row["source"]), height=0.55)
        ax.bar_label(
            bar,
            labels=[f"{row['mean_difference_pct']:+.1f}%  ({row['shared_games']:,} shared games)"],
            padding=6,
            color=INK,
            fontsize=10,
        )

    _style(ax, "Regular price of the same games, against the other stores", "Average price difference (%)", "")
    ax.grid(axis="y", visible=False)
    ax.axvline(0, color=MUTED, linewidth=1)
    if comparison.empty:
        ax.text(0.5, 0.5, "No games shared between storefronts", transform=ax.transAxes, ha="center", color=MUTED)
    else:
        reach = max(float(comparison["mean_difference_pct"].abs().max()), 1.0)
        ax.set_xlim(-reach * 1.6, reach * 3.2)  # room on the right for the labels
    return _save(fig, output_dir, "cross_store_prices.png")
