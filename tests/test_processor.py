import pandas as pd

from gameprice_index.processor import (
    clean_price_columns,
    combine_and_format_data,
    process_nintendo_data,
    process_playstation_data,
)


def test_clean_price_columns():
    """Tests that currency symbols and asterisks are stripped and types converted to float."""
    raw_data = {"price": ["£49.99", "*39.99", "Free", ""], "price_old": ["£59.99", "£49.99", None, ""]}
    df = pd.DataFrame(raw_data)
    cleaned_df = clean_price_columns(df)

    assert cleaned_df["price"][0] == 49.99
    assert cleaned_df["price"][1] == 39.99
    assert pd.isna(cleaned_df["price"][2])
    assert pd.isna(cleaned_df["price"][3])

    assert cleaned_df["price_old"][0] == 59.99
    assert pd.isna(cleaned_df["price_old"][2])


def test_discount_calculation():
    """Tests that combining datasets correctly calculates the discount_amount."""
    # mock nintendo data
    nintendo_data = {
        "name": ["Mario Kart"],
        "price": [40.00],
        "price_old": [50.00],
        "source": ["Nintendo"],
        "platform": ["Nintendo Switch"],
        "nsuid": ["12345"],
        "product_code": [None],
        "badge": [None],
        "date_range": [None],
        "url": ["https://nintendo.com/mario"],
        "out_of_stock": [False],
    }
    # mock playStation data
    ps_data = {
        "name": ["Spider-Man"],
        "price": [60.00],
        "price_old": [70.00],
        "source": ["PlayStation"],
        "platform": ["PS5"],
        "nsuid": [None],
        "product_code": ["P-123"],
        "badge": [None],
        "date_range": [None],
        "url": ["https://playstation.com/spidey"],
        "out_of_stock": [False],
    }

    df_n = pd.DataFrame(nintendo_data)
    df_p = pd.DataFrame(ps_data)

    final_df = combine_and_format_data(df_n, df_p)

    assert len(final_df) == 2
    assert "discount_amount" in final_df.columns

    mario = final_df[final_df["name"] == "Mario Kart"].iloc[0]
    assert mario["discount_amount"] == 10.00

    spidey = final_df[final_df["name"] == "Spider-Man"].iloc[0]
    assert spidey["discount_amount"] == 10.00


def test_discount_amount_is_never_negative():
    """Regression: a sale price above the original price means the columns are swapped."""
    df = pd.read_csv("data/data.csv")
    discounts = df["discount_amount"].dropna()

    assert not discounts.empty
    assert (discounts >= 0).all()


def test_nintendo_rows_without_nsuid_are_dropped():
    """Tiles with no nsuid cannot be priced and must not end up as a 'None' id."""
    base = [
        {
            "name": "Mario Kart World",
            "platform": "Nintendo Switch 2",
            "nsuid": "70010000096802",
            "price": None,
            "price_old": None,
        },
        {"name": "Farm 2+", "platform": "Nintendo Switch", "nsuid": None, "price": None, "price_old": None},
        {"name": "Blank", "platform": "Nintendo Switch", "nsuid": "", "price": None, "price_old": None},
    ]
    prices = [{"nsuid": "70010000096802", "price": "£66.99", "price_old": None}]

    df = process_nintendo_data(base, prices)

    assert df["name"].tolist() == ["Mario Kart World"]
    assert df["product_code"].tolist() == ["70010000096802"]
    assert df["price"].tolist() == [66.99]


def _nintendo_base(**overrides):
    row = {
        "name": "Mario Kart World",
        "platform": "  Nintendo Switch 2 ",
        "url": "https://example.test/mk",
        "nsuid": "70010000096802",
        "price": None,
        "price_old": None,
        "badge": None,
        "date_range": None,
        "product_code": None,
        "out_of_stock": None,
        "source": "Nintendo",
    }
    row.update(overrides)
    return row


def test_process_nintendo_data_merges_prices_by_nsuid():
    base = [_nintendo_base(), _nintendo_base(name="Kero Kero Cowboy", nsuid="70010000126803")]
    prices = [
        {"nsuid": "70010000126803", "price": "£7.64", "price_old": "£8.99"},
        {"nsuid": "70010000096802", "price": "£66.99*", "price_old": None},
    ]

    df = process_nintendo_data(base, prices)

    assert df["name"].tolist() == ["Mario Kart World", "Kero Kero Cowboy"]
    assert df["price"].tolist() == [66.99, 7.64]
    assert pd.isna(df["price_old"][0])
    assert df["price_old"][1] == 8.99
    assert df["platform"][0] == "Nintendo Switch 2"
    assert "price_new" not in df.columns


def test_process_nintendo_data_uses_first_nsuid_as_product_code():
    """Multi-edition games carry several nsuids; the first is the base game."""
    base = [_nintendo_base(nsuid="70010000115568|70050000069174")]
    prices = [{"nsuid": "70010000115568|70050000069174", "price": "£16.99", "price_old": None}]

    df = process_nintendo_data(base, prices)

    assert df["nsuid"].tolist() == ["70010000115568"]
    assert df["product_code"].tolist() == ["70010000115568"]
    assert df["price"].tolist() == [16.99]


def test_process_nintendo_data_leaves_unpriced_games_empty():
    base = [_nintendo_base(), _nintendo_base(name="Unpriced", nsuid="70010000000001")]
    prices = [{"nsuid": "70010000096802", "price": "£66.99", "price_old": None}]

    df = process_nintendo_data(base, prices)

    assert df["price"][0] == 66.99
    assert pd.isna(df["price"][1])


def test_process_nintendo_data_without_price_records():
    df = process_nintendo_data([_nintendo_base()], [])

    assert len(df) == 1
    assert pd.isna(df["price"][0])
    assert df["product_code"][0] == "70010000096802"


def test_process_nintendo_data_with_no_games():
    assert process_nintendo_data([], []).empty


def test_process_playstation_data_cleans_prices():
    ps = [{"name": "Astro Bot - PS5", "price": "£39.99", "price_old": "£59.99", "source": "PlayStation"}]

    df = process_playstation_data(ps)

    assert df["price"].tolist() == [39.99]
    assert df["price_old"].tolist() == [59.99]
    assert process_playstation_data([]).empty
