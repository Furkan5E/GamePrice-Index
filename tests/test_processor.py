import pandas as pd
import pytest

from gameprice_index.processor import COLUMNS, add_discount, build_frame, clean_price_columns, combine_frames


def _record(**overrides):
    record = {
        "source": "Nintendo",
        "platform": "Nintendo Switch 2",
        "product_code": "70010000096802",
        "name": "Mario Kart World",
        "price": "£66.99",
        "price_old": None,
        "badge": None,
        "out_of_stock": None,
        "url": "https://example.test/mk",
    }
    record.update(overrides)
    return record


def test_clean_price_columns():
    """Currency symbols, asterisks and thousands separators are stripped and values become floats."""
    df = pd.DataFrame(
        {
            "price": ["£49.99", "*39.99", "Free", "", "£1,299.00", 12.5],
            "price_old": ["£59.99", "£49.99", None, "", None, None],
        }
    )
    cleaned = clean_price_columns(df)

    assert cleaned["price"].tolist()[:2] == [49.99, 39.99]
    assert pd.isna(cleaned["price"][2])
    assert pd.isna(cleaned["price"][3])
    assert cleaned["price"][4] == 1299.0
    assert cleaned["price"][5] == 12.5
    assert cleaned["price_old"][0] == 59.99
    assert pd.isna(cleaned["price_old"][2])


def test_build_frame_has_the_final_columns():
    df = build_frame([_record()])

    assert df.columns.tolist() == COLUMNS
    assert df["price"].tolist() == [66.99]
    assert df["product_code"].tolist() == ["70010000096802"]


def test_build_frame_computes_discount():
    df = build_frame([_record(price="£7.64", price_old="£8.99")])

    assert df["discount_amount"].tolist() == [1.35]
    assert df["discount_pct"].tolist() == [15.0]


def test_build_frame_ignores_old_price_that_is_not_higher():
    """Some stores send the regular price twice when nothing is on sale."""
    df = build_frame(
        [
            _record(product_code="1", price="£9.99", price_old="£9.99"),
            _record(product_code="2", price="£9.99", price_old="£4.99"),
        ]
    )

    assert df["price_old"].isna().all()
    assert df["discount_amount"].isna().all()
    assert df["discount_pct"].isna().all()


def test_build_frame_strips_whitespace():
    df = build_frame([_record(name="  Mario Kart World\t", platform=" Nintendo Switch 2 ")])

    assert df["name"].tolist() == ["Mario Kart World"]
    assert df["platform"].tolist() == ["Nintendo Switch 2"]


def test_build_frame_drops_unidentifiable_rows():
    """Regression: rows with no id used to be kept and stored under the id 'None'."""
    df = build_frame(
        [
            _record(),
            _record(product_code=None, name="No Code"),
            _record(product_code="  ", name="Blank Code"),
            _record(product_code="123", name=None),
        ]
    )

    assert df["name"].tolist() == ["Mario Kart World"]


def test_build_frame_removes_duplicate_products():
    df = build_frame([_record(), _record(price="£1.00")])

    assert len(df) == 1
    assert df["price"].tolist() == [66.99]


def test_build_frame_keeps_unknown_stock_distinct_from_in_stock():
    df = build_frame(
        [
            _record(product_code="1", out_of_stock=None),
            _record(product_code="2", out_of_stock=False),
            _record(product_code="3", out_of_stock=True),
        ]
    )

    assert str(df["out_of_stock"].dtype) == "boolean"
    assert pd.isna(df["out_of_stock"][0])
    assert df["out_of_stock"].tolist()[1:] == [False, True]


def test_build_frame_with_no_records():
    df = build_frame([])

    assert df.empty
    assert df.columns.tolist() == COLUMNS


def test_add_discount_is_never_negative():
    df = pd.DataFrame({"price": [10.0, 10.0, 10.0], "price_old": [15.0, 5.0, None]})

    discounts = add_discount(df)["discount_amount"]

    assert discounts[0] == 5.0
    assert discounts.dropna().ge(0).all()
    assert discounts.isna().sum() == 2


def test_combine_frames_stacks_sources():
    nintendo = build_frame([_record(price="£40.00", price_old="£50.00")])
    playstation = build_frame(
        [_record(source="PlayStation", platform="PS5", product_code="P-123", name="Spider-Man", price="£60.00")]
    )

    df = combine_frames([nintendo, playstation, build_frame([])])

    assert df["source"].tolist() == ["Nintendo", "PlayStation"]
    assert df["discount_amount"][0] == 10.0
    assert df.columns.tolist() == COLUMNS


def test_combine_frames_with_nothing():
    assert combine_frames([]).columns.tolist() == COLUMNS


def test_committed_dataset_has_no_negative_discounts():
    """Regression: a sale price above the original price means the columns are swapped."""
    df = pd.read_csv("data/data.csv")
    discounts = df["discount_amount"].dropna()

    assert not discounts.empty
    assert (discounts >= 0).all()
    assert df.columns.tolist() == COLUMNS


@pytest.mark.parametrize("column", ["source", "product_code", "name"])
def test_committed_dataset_identifies_every_row(column):
    df = pd.read_csv("data/data.csv", dtype={"product_code": "string"})

    assert df[column].notna().all()
