import pandas as pd
import pytest
from src.processor import clean_price_columns, combine_and_format_data

def test_clean_price_columns():
    """Tests that currency symbols and asterisks are stripped and types converted to float."""
    raw_data = {
        "price": ["£49.99", "*39.99", "Free", ""],
        "price_old": ["£59.99", "£49.99", None, ""]
    }
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
    #mock nintendo data
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
        "out_of_stock": [False]
    }
    #mock playStation data
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
        "out_of_stock": [False]
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