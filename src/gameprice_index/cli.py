import argparse
import logging
import os
import sys
from collections.abc import Sequence

import pandas as pd

from gameprice_index import config
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

SOURCES = ("nintendo", "playstation")


def configure_logging() -> None:
    """Sets up logging once for the whole pipeline; modules only create loggers."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ids are digit strings; left to pandas they become floats as soon as one is missing
ID_COLUMN_TYPES = {"nsuid": "string", "product_code": "string"}


def load_cache(path: str) -> pd.DataFrame:
    """Reads a cached CSV, failing clearly if it is missing or a previous run left it empty."""
    try:
        return pd.read_csv(path, dtype=ID_COLUMN_TYPES)
    except FileNotFoundError as e:
        raise ScrapeError(f"No cached file at {path}; run without --cached to create it.") from e
    except pd.errors.EmptyDataError as e:
        raise ScrapeError(f"Cached file {path} is empty; run without --cached to rebuild it.") from e


def write_cache(df: pd.DataFrame, path: str) -> None:
    """Writes a cached CSV, never replacing good data with an empty scrape."""
    if df.empty:
        raise ScrapeError(f"Refusing to overwrite {path} with an empty dataset.")
    df.to_csv(path, index=False)


def scrape_source(source: str) -> pd.DataFrame:
    """Scrapes one storefront and returns its processed dataframe."""
    if source == "nintendo":
        nintendo_base = scrape_nintendo_base(config.NINTENDO_URL)
        nintendo_prices = scrape_nintendo_prices(config.NINTENDO_URL)
        return process_nintendo_data(nintendo_base, nintendo_prices)
    if source == "playstation":
        return process_playstation_data(scrape_playstation(config.PLAYSTATION_URL))
    raise ValueError(f"Unknown source: {source}")


def run_pipeline(
    use_cache: bool = False,
    sources: Sequence[str] = SOURCES,
    make_plots: bool = True,
) -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)

    cache_paths = {source: os.path.join(config.DATA_DIR, config.CACHE_NAMES[source]) for source in sources}
    final_data_path = os.path.join(config.DATA_DIR, config.FINAL_CSV_NAME)
    db_path = os.path.join(config.DATA_DIR, config.DATABASE_NAME)

    if use_cache:
        logger.info("Loading cached processed data from data/ directory.")
        frames = {source: load_cache(cache_paths[source]) for source in sources}
    else:
        logger.info(f"Starting live web scraping for: {', '.join(sources)}")
        frames = {source: scrape_source(source) for source in sources}

        # only touch the cache once every requested source has succeeded
        for source in sources:
            write_cache(frames[source], cache_paths[source])

    # Combine & Compute Metrics
    df_final = combine_and_format_data(
        frames.get("nintendo", pd.DataFrame()),
        frames.get("playstation", pd.DataFrame()),
    )

    # save to both CSV and DB
    save_data(df_final, db_path=db_path, csv_path=final_data_path, write_db=not use_cache)
    logger.info(f"Saved master dataset to {final_data_path}")

    # Generate Visualizations
    if make_plots:
        plot_platform_distribution(df_final, output_dir=config.PLOTS_DIR)
        plot_price_analysis(df_final, output_dir=config.PLOTS_DIR)
        plot_price_vs_discount(df_final, output_dir=config.PLOTS_DIR)
    else:
        logger.info("Skipping plots.")
    logger.info("Pipeline executed successfully!")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gameprice-index", description="GamePrice-Index ETL & Analysis Pipeline")
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Use existing processed CSV files in data/ instead of scraping live sites.",
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=SOURCES,
        dest="sources",
        help="Storefront to include; repeat for several. Defaults to all of them.",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip generating the plots.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Console entry point; returns the process exit code."""
    args = build_parser().parse_args(argv)

    configure_logging()
    try:
        run_pipeline(
            use_cache=args.cached,
            sources=tuple(args.sources or SOURCES),
            make_plots=not args.no_plots,
        )
    except ScrapeError as e:
        logger.error(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
