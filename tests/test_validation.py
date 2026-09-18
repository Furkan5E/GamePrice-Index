import pandas as pd
import pytest

from gameprice_index.processor import COLUMNS, build_frame
from gameprice_index.validation import DataValidationError, validate_dataset


def _records(count: int = 4):
    return [
        {
            "source": "Nintendo",
            "platform": "Nintendo Switch",
            "product_code": f"7001000000000{n}",
            "name": f"Game {n}",
            "price": 10.0 + n,
            "price_old": 20.0 + n if n % 2 else None,
            "badge": None,
            "out_of_stock": None,
            "url": f"https://example.test/{n}",
        }
        for n in range(count)
    ]


@pytest.fixture
def df() -> pd.DataFrame:
    return build_frame(_records())


def test_clean_dataset_passes(df):
    validated = validate_dataset(df)

    assert validated.columns.tolist() == COLUMNS
    assert len(validated) == 4


def test_committed_dataset_passes():
    df = pd.read_csv("data/data.csv", dtype={"product_code": "string", "out_of_stock": "boolean"})

    assert len(validate_dataset(df, "data/data.csv")) == len(df)


def test_cached_csv_dtypes_are_coerced(df, tmp_path):
    """A CSV round trip turns empty text columns into floats; validation must cope."""
    path = tmp_path / "cache.csv"
    df.to_csv(path, index=False)

    validated = validate_dataset(pd.read_csv(path, dtype={"product_code": "string"}))

    assert str(validated["out_of_stock"].dtype) == "boolean"
    assert validated["price"].tolist() == df["price"].tolist()


def test_negative_price_is_rejected(df):
    """Regression: the Nintendo index reports -1 for games without a price."""
    df.loc[0, "price"] = -1.0

    with pytest.raises(DataValidationError, match="price"):
        validate_dataset(df)


def test_swapped_sale_price_is_rejected(df):
    """Regression: Nintendo sale and regular prices were once stored the wrong way round."""
    df.loc[1, ["price", "price_old"]] = [21.0, 11.0]

    with pytest.raises(DataValidationError, match="price_old must be higher than price"):
        validate_dataset(df)


def test_stale_discount_is_rejected(df):
    df.loc[1, "discount_amount"] = 3.0

    with pytest.raises(DataValidationError, match="discount_amount must equal"):
        validate_dataset(df)


def test_missing_id_is_rejected(df):
    """Regression: rows without an id used to be stored under the literal id 'None'."""
    df.loc[2, "product_code"] = None

    with pytest.raises(DataValidationError, match="product_code"):
        validate_dataset(df)


def test_duplicate_product_is_rejected(df):
    df.loc[3, "product_code"] = df.loc[2, "product_code"]

    with pytest.raises(DataValidationError, match="product_code"):
        validate_dataset(df)


def test_implausible_price_is_rejected(df):
    df.loc[0, "price"] = 49_999.0

    with pytest.raises(DataValidationError, match="in_range"):
        validate_dataset(df)


def test_relative_url_is_rejected(df):
    df.loc[0, "url"] = "/en-gb/games/some-game"

    with pytest.raises(DataValidationError, match="url"):
        validate_dataset(df)


def test_unexpected_column_is_rejected(df):
    df["nsuid"] = "1"

    with pytest.raises(DataValidationError):
        validate_dataset(df)


def test_mostly_unpriced_source_is_rejected(df):
    """A source that suddenly has no prices means its price parsing broke."""
    df.loc[:2, ["price", "price_old", "discount_amount", "discount_pct"]] = None

    with pytest.raises(DataValidationError, match=r"too many games without a price: Nintendo \(75%\)"):
        validate_dataset(df)


def test_error_message_names_the_dataset_and_gives_examples(df):
    df.loc[0, "price"] = -1.0

    with pytest.raises(DataValidationError) as error:
        validate_dataset(df, "Nintendo data")

    message = str(error.value)
    assert message.startswith("Nintendo data failed validation:")
    assert "-1.0" in message
