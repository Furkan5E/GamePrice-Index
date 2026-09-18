"""Schema checks that stop bad data before it is cached, stored or plotted.

Every rule here exists because the data broke it at some point: sale prices
above the regular price, rows with no id, and prices of -1 for unreleased games.
"""

import logging

import pandas as pd
import pandera.pandas as pa

from gameprice_index.processor import COLUMNS

logger = logging.getLogger(__name__)

MAX_PLAUSIBLE_PRICE = 2000  # pounds; anything above is a parsing mistake, not a game
MAX_UNPRICED_SHARE = 0.5  # a source where most games have no price was probably parsed wrongly
MAX_REPORTED_FAILURES = 10


class DataValidationError(RuntimeError):
    """Raised when a dataset breaks the schema."""


def _old_price_is_higher(df: pd.DataFrame) -> pd.Series:
    """An old price only makes sense if the game is cheaper now."""
    return df["price_old"].isna() | (df["price_old"] > df["price"])


def _discount_matches_prices(df: pd.DataFrame) -> pd.Series:
    expected = (df["price_old"] - df["price"]).round(2)
    return df["discount_amount"].isna() & expected.isna() | ((df["discount_amount"] - expected).abs() < 0.011)


DATASET_SCHEMA = pa.DataFrameSchema(
    columns={
        "source": pa.Column(str, pa.Check.str_length(min_value=1)),
        "platform": pa.Column(str, nullable=True),
        "product_code": pa.Column(str, pa.Check.str_length(min_value=1)),
        "name": pa.Column(str, pa.Check.str_length(min_value=1)),
        "price": pa.Column(float, pa.Check.in_range(0, MAX_PLAUSIBLE_PRICE), nullable=True),
        "price_old": pa.Column(float, pa.Check.in_range(0, MAX_PLAUSIBLE_PRICE), nullable=True),
        "discount_amount": pa.Column(float, pa.Check.gt(0), nullable=True),
        "discount_pct": pa.Column(float, pa.Check.in_range(0, 100, include_min=False), nullable=True),
        "badge": pa.Column(str, nullable=True),
        "out_of_stock": pa.Column("boolean", nullable=True),
        "url": pa.Column(str, pa.Check.str_startswith("http"), nullable=True),
    },
    checks=[
        pa.Check(_old_price_is_higher, error="price_old must be higher than price"),
        pa.Check(_discount_matches_prices, error="discount_amount must equal price_old - price"),
    ],
    unique=["source", "product_code"],
    coerce=True,
    strict=True,
)

assert list(DATASET_SCHEMA.columns) == COLUMNS, "schema and dataset columns have drifted apart"


def _summarise(failures: pd.DataFrame) -> str:
    """Condenses pandera's failure table into a few readable lines."""
    lines = []
    grouped = failures.groupby(["column", "check"], dropna=False, sort=False)
    for (column, check), rows in list(grouped)[:MAX_REPORTED_FAILURES]:
        examples = ", ".join(str(value) for value in rows["failure_case"].head(3))
        where = column if isinstance(column, str) else "dataset"
        lines.append(f"  - {where}: {check} ({len(rows)} rows, e.g. {examples})")
    return "\n".join(lines)


def validate_dataset(df: pd.DataFrame, label: str = "dataset") -> pd.DataFrame:
    """Returns the dataframe with schema dtypes, or raises DataValidationError listing what is wrong."""
    try:
        validated = DATASET_SCHEMA.validate(df, lazy=True)
    except pa.errors.SchemaErrors as e:
        raise DataValidationError(f"{label} failed validation:\n{_summarise(e.failure_cases)}") from e

    unpriced = validated.groupby("source")["price"].apply(lambda prices: prices.isna().mean())
    suspicious = unpriced[unpriced > MAX_UNPRICED_SHARE]
    if not suspicious.empty:
        detail = ", ".join(f"{source} ({share:.0%})" for source, share in suspicious.items())
        raise DataValidationError(f"{label} failed validation:\n  - too many games without a price: {detail}")

    logger.info(f"Validated {label}: {len(validated)} rows.")
    return validated
