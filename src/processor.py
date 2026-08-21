import pandas as pd
import logging
import sqlite3
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def clean_price_columns(df: pd.DataFrame, price_cols: tuple = ("price", "price_old")) -> pd.DataFrame:
    """Removes currency symbols and converts price columns to numeric."""
    for col in price_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace("£", "", regex=False)
                .str.replace("*", "", regex=False)
                .str.strip()
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def process_nintendo_data(base_data: List[Dict[str, Any]], price_data: List[Dict[str, Any]]) -> pd.DataFrame:
    """Merges and cleans Nintendo base and dynamic pricing data."""
    logger.info("Processing Nintendo data.")
    df_base = pd.DataFrame(base_data)
    df_prices = pd.DataFrame(price_data)

    if df_base.empty:
        logger.warning("Nintendo base data is empty.")
        return df_base

    if not df_prices.empty:
        df_nintendo = df_base.merge(df_prices, on="nsuid", how="left", suffixes=("", "_new"))
        
        for col in ["price", "price_old"]:
            df_nintendo[col] = df_nintendo[col].fillna(df_nintendo[f"{col}_new"])
            df_nintendo[col] = df_nintendo[col].replace("", pd.NA)
            df_nintendo[col] = df_nintendo[col].fillna(df_nintendo[f"{col}_new"])
            
        df_nintendo.drop(columns=["price_new", "price_old_new"], inplace=True, errors="ignore")
    else:
        df_nintendo = df_base

    df_nintendo["nsuid"] = df_nintendo["nsuid"].astype(str).str.split("|").str[0]
    df_nintendo["product_code"] = df_nintendo["nsuid"]
    df_nintendo["platform"] = df_nintendo["platform"].astype(str).str.split("â").str[0].str.strip()
    
    df_nintendo = clean_price_columns(df_nintendo)
    return df_nintendo

def process_playstation_data(ps_data: List[Dict[str, Any]]) -> pd.DataFrame:
    """Cleans and standardizes PlayStation data."""
    logger.info("Processing PlayStation data.")
    df_ps = pd.DataFrame(ps_data)
    
    if df_ps.empty:
        logger.warning("PlayStation data is empty.")
        return df_ps

    df_ps = clean_price_columns(df_ps)
    return df_ps

def combine_and_format_data(df_nintendo: pd.DataFrame, df_ps: pd.DataFrame) -> pd.DataFrame:
    """Combines platform data and computes final metrics."""
    logger.info("Combining Nintendo and PlayStation datasets.")
    
    common_cols = [
        "name", "price", "price_old", "badge", "date_range",
        "url", "product_code", "out_of_stock",
        "platform", "nsuid", "source"
    ]
    
    df_n_final = df_nintendo[common_cols] if not df_nintendo.empty else pd.DataFrame(columns=common_cols)
    df_p_final = df_ps[common_cols] if not df_ps.empty else pd.DataFrame(columns=common_cols)
    
    df_final = pd.concat([df_p_final, df_n_final], ignore_index=True)
    
    df_final["discount_amount"] = df_final["price_old"] - df_final["price"]
    
    logger.info(f"Data processing complete. Final dataset contains {len(df_final)} rows.")
    return df_final

def save_data(df: pd.DataFrame, db_path: str = "data/game_prices.db", csv_path: str = "data/final_prices.csv"):
    """Saves the final dataframe to both a CSV and an SQLite database."""
    logger.info(f"Saving data to {csv_path} and {db_path}...")
    
    df.to_csv(csv_path, index=False)

    try:
        with sqlite3.connect(db_path) as conn:
            # Create a copy so the timestamp column isn't passed to the plotting functions
            df_db = df.copy()
            df_db['scrape_timestamp'] = pd.Timestamp.now() 
            df_db.to_sql('prices', conn, if_exists='append', index=False)
        logger.info("Data successfully saved to database.")
    except Exception as e:
        logger.error(f"Failed to save to database: {e}")