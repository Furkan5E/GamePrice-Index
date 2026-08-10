import os
import argparse
import logging
import pandas as pd

from src.scraper import (
    scrape_nintendo_base,
    scrape_nintendo_prices,
    scrape_playstation
)
from src.processor import (
    process_nintendo_data,
    process_playstation_data,
    combine_and_format_data
)
from src.visualiser import (
    plot_platform_distribution,
    plot_price_analysis,
    plot_price_vs_discount
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

NINTENDO_URL = "https://www.nintendo.com/en-gb/Games"
PLAYSTATION_URL = "https://direct.playstation.com/en-gb/games/"

def run_pipeline(use_cache: bool = False):
    os.makedirs("data", exist_ok=True)
    os.makedirs("plots", exist_ok=True)

    raw_nintendo_path = os.path.join("data", "raw_nintendo.csv")
    raw_ps_path = os.path.join("data", "raw_ps.csv")
    final_data_path = os.path.join("data", "data.csv")

    if use_cache and os.path.exists(raw_nintendo_path) and os.path.exists(raw_ps_path):
        logger.info("Loading cached raw data from data/ directory.")
        df_nintendo_processed = pd.read_csv(raw_nintendo_path)
        df_ps_processed = pd.read_csv(raw_ps_path)
    else:
        logger.info("Starting live web scraping...")
        # 1. Scrape Nintendo
        nintendo_base = scrape_nintendo_base(NINTENDO_URL)
        nintendo_prices = scrape_nintendo_prices(NINTENDO_URL)
        df_nintendo_processed = process_nintendo_data(nintendo_base, nintendo_prices)
        df_nintendo_processed.to_csv(raw_nintendo_path, index=False)
        
        # 2. Scrape PlayStation
        ps_data = scrape_playstation(PLAYSTATION_URL)
        df_ps_processed = process_playstation_data(ps_data)
        df_ps_processed.to_csv(raw_ps_path, index=False)

    # 3. Combine & Compute Metrics
    df_final = combine_and_format_data(df_nintendo_processed, df_ps_processed)
    df_final.to_csv(final_data_path, index=False)
    logger.info(f"Saved master dataset to {final_data_path}")

    # 4. Generate Visualizations
    plot_platform_distribution(df_final)
    plot_price_analysis(df_final)
    plot_price_vs_discount(df_final)
    logger.info("Pipeline executed successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GamePrice-Index ETL & Analysis Pipeline")
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Use existing raw CSV files in data/ instead of scraping live sites."
    )
    args = parser.parse_args()
    
    run_pipeline(use_cache=args.cached)