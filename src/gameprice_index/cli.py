import argparse
import logging
import os
import sys

import pandas as pd

from gameprice_index.processor import (
    combine_and_format_data,
    process_nintendo_data,
    process_playstation_data,
    save_data,
)
from gameprice_index.scraper import (
    ScrapeError,
    scrape_nintendo_base,
    scrape_nintendo_prices,
    scrape_playstation,
)
from gameprice_index.visualiser import plot_platform_distribution, plot_price_analysis, plot_price_vs_discount

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Sets up logging once for the whole pipeline; modules only create loggers."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


NINTENDO_URL = "https://www.nintendo.com/en-gb/Games"
PLAYSTATION_URL = "https://direct.playstation.com/en-gb/games/"

# ids are digit strings; left to pandas they become floats as soon as one is missing
ID_COLUMN_TYPES = {"nsuid": "string", "product_code": "string"}


def load_cache(path: str) -> pd.DataFrame:
    """Reads a cached CSV, failing clearly if a previous run left it empty."""
    try:
        return pd.read_csv(path, dtype=ID_COLUMN_TYPES)
    except pd.errors.EmptyDataError as e:
        raise ScrapeError(f"Cached file {path} is empty; run without --cached to rebuild it.") from e


def write_cache(df: pd.DataFrame, path: str) -> None:
    """Writes a cached CSV, never replacing good data with an empty scrape."""
    if df.empty:
        raise ScrapeError(f"Refusing to overwrite {path} with an empty dataset.")
    df.to_csv(path, index=False)


def run_pipeline(use_cache: bool = False) -> None:
    os.makedirs("data", exist_ok=True)
    os.makedirs("plots", exist_ok=True)

    nintendo_cache_path = os.path.join("data", "processed_nintendo.csv")
    ps_cache_path = os.path.join("data", "processed_playstation.csv")
    final_data_path = os.path.join("data", "data.csv")

    loaded_from_cache = use_cache and os.path.exists(nintendo_cache_path) and os.path.exists(ps_cache_path)

    if loaded_from_cache:
        logger.info("Loading cached processed data from data/ directory.")
        df_nintendo_processed = load_cache(nintendo_cache_path)
        df_ps_processed = load_cache(ps_cache_path)
    else:
        logger.info("Starting live web scraping...")
        # 1. Scrape Nintendo
        nintendo_base = scrape_nintendo_base(NINTENDO_URL)
        nintendo_prices = scrape_nintendo_prices(NINTENDO_URL)
        df_nintendo_processed = process_nintendo_data(nintendo_base, nintendo_prices)

        # 2. Scrape PlayStation
        ps_data = scrape_playstation(PLAYSTATION_URL)
        df_ps_processed = process_playstation_data(ps_data)

        # only touch the cache once every source has succeeded
        write_cache(df_nintendo_processed, nintendo_cache_path)
        write_cache(df_ps_processed, ps_cache_path)

    # 3. Combine & Compute Metrics
    df_final = combine_and_format_data(df_nintendo_processed, df_ps_processed)

    # save to both CSV and DB
    save_data(df_final, csv_path=final_data_path, write_db=not loaded_from_cache)
    logger.info(f"Saved master dataset to {final_data_path}")

    # 4. Generate Visualizations
    plot_platform_distribution(df_final)
    plot_price_analysis(df_final)
    plot_price_vs_discount(df_final)
    logger.info("Pipeline executed successfully!")


def main(argv=None) -> int:
    """Console entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(prog="gameprice-index", description="GamePrice-Index ETL & Analysis Pipeline")
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Use existing processed CSV files in data/ instead of scraping live sites.",
    )
    args = parser.parse_args(argv)

    configure_logging()
    try:
        run_pipeline(use_cache=args.cached)
    except ScrapeError as e:
        logger.error(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
