"""Turns raw scraper records into one clean, comparable dataset."""

import logging
from collections.abc import Iterable
from typing import Any

import pandas as pd

from gameprice_index.scrapers.base import RECORD_FIELDS

logger = logging.getLogger(__name__)

# column order of the final dataset
COLUMNS = [
    "source",
    "platform",
    "product_code",
    "name",
    "price",
    "price_old",
    "discount_amount",
    "badge",
    "out_of_stock",
    "url",
]


def clean_price_columns(df: pd.DataFrame, price_cols: tuple = ("price", "price_old")) -> pd.DataFrame:
    """Removes currency symbols and converts price columns to numeric."""
    for col in price_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace("£", "", regex=False)
                .str.replace("*", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def add_discount(df: pd.DataFrame) -> pd.DataFrame:
    """Computes the discount, treating an old price that is not higher as no discount at all."""
    on_sale = df["price_old"].notna() & df["price"].notna() & (df["price_old"] > df["price"])
    df["price_old"] = df["price_old"].where(on_sale)
    df["discount_amount"] = (df["price_old"] - df["price"]).round(2)
    return df


def build_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Cleans one source's records into a dataframe with the final columns."""
    df = pd.DataFrame(records, columns=list(RECORD_FIELDS))
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    for col in ("name", "platform", "product_code"):
        df[col] = df[col].astype("string").str.strip()

    # a product that cannot be identified cannot be tracked over time
    identified = df["product_code"].notna() & (df["product_code"] != "") & df["name"].notna()
    if not identified.all():
        logger.warning(f"Dropping {(~identified).sum()} rows without a product code or name.")
    df = df[identified].drop_duplicates(subset=["source", "product_code"]).reset_index(drop=True)

    # a nullable boolean keeps "unknown" distinct from False and survives a CSV round trip
    df["out_of_stock"] = df["out_of_stock"].astype("boolean")

    df = clean_price_columns(df)
    df = add_discount(df)
    return df[COLUMNS]


def combine_frames(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """Stacks the per-source dataframes into the final dataset."""
    frames = [frame[COLUMNS] for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=COLUMNS)

    df_final = pd.concat(frames, ignore_index=True)
    logger.info(f"Data processing complete. Final dataset contains {len(df_final)} rows.")
    return df_final
