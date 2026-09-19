import argparse
import logging
import os
import sys
from collections.abc import Sequence

import pandas as pd

from gameprice_index import config, storage
from gameprice_index.matching import cross_store_prices, store_comparison
from gameprice_index.processor import build_frame, combine_frames
from gameprice_index.scrapers import SCRAPERS, ScrapeError, get_scraper
from gameprice_index.validation import DataValidationError, validate_dataset
from gameprice_index.visualiser import (
    plot_cross_store_prices,
    plot_platform_distribution,
    plot_price_analysis,
    plot_price_vs_discount,
    sources_in,
)

logger = logging.getLogger(__name__)

SOURCES = tuple(SCRAPERS)

EXIT_SCRAPE_FAILED = 1
EXIT_INVALID_DATA = 2


def configure_logging() -> None:
    """Sets up logging once for the whole pipeline; modules only create loggers."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# left to pandas, digit-only ids become floats and a column of unknown stock levels becomes NaN
CACHE_COLUMN_TYPES = {"product_code": "string", "out_of_stock": "boolean"}


def cache_path(data_dir: str, source: str) -> str:
    """Returns where the processed data of one source is cached."""
    return os.path.join(data_dir, f"processed_{source}.csv")


def load_cache(path: str) -> pd.DataFrame:
    """Reads a cached CSV, failing clearly if it is missing or a previous run left it empty."""
    try:
        return pd.read_csv(path, dtype=CACHE_COLUMN_TYPES)
    except FileNotFoundError as e:
        raise ScrapeError(f"No cached file at {path}; run without --cached to create it.") from e
    except pd.errors.EmptyDataError as e:
        raise ScrapeError(f"Cached file {path} is empty; run without --cached to rebuild it.") from e


def write_cache(df: pd.DataFrame, path: str) -> None:
    """Writes a cached CSV, never replacing good data with an empty scrape."""
    if df.empty:
        raise ScrapeError(f"Refusing to overwrite {path} with an empty dataset.")
    df.to_csv(path, index=False)


def scrape_source(source: str, limit: int | None = config.DEFAULT_LIMIT) -> pd.DataFrame:
    """Scrapes one storefront and returns its processed dataframe."""
    scraper = get_scraper(source)(limit=limit)
    return build_frame(scraper.scrape())


def run_pipeline(
    use_cache: bool = False,
    sources: Sequence[str] = SOURCES,
    make_plots: bool = True,
    output_dir: str = ".",
    db_path: str | None = None,
    limit: int | None = config.DEFAULT_LIMIT,
) -> None:
    data_dir = os.path.join(output_dir, config.DATA_DIR)
    plots_dir = os.path.join(output_dir, config.PLOTS_DIR)
    os.makedirs(data_dir, exist_ok=True)

    final_data_path = os.path.join(data_dir, config.FINAL_CSV_NAME)
    db_path = db_path or os.path.join(data_dir, config.DATABASE_NAME)

    if use_cache:
        logger.info(f"Loading cached processed data from {data_dir}")
        frames = {source: load_cache(cache_path(data_dir, source)) for source in sources}
    else:
        logger.info(f"Starting live web scraping for: {', '.join(sources)}")
        frames = {source: scrape_source(source, limit=limit) for source in sources}

    # a source that parses but produces nonsense must not get any further
    frames = {source: validate_dataset(frame, f"{source} data") for source, frame in frames.items()}

    if not use_cache:
        # only touch the cache once every requested source has succeeded and passed validation
        for source in sources:
            write_cache(frames[source], cache_path(data_dir, source))

    df_final = validate_dataset(combine_frames(frames.values()), "combined dataset")
    df_final.to_csv(final_data_path, index=False)
    logger.info(f"Saved master dataset to {final_data_path}")

    # the same games on different stores, for a like-for-like comparison
    matched = cross_store_prices(df_final)
    matched.to_csv(os.path.join(data_dir, config.CROSS_STORE_CSV_NAME), index=False)

    # cached data was already recorded when it was scraped, so only fresh scrapes go into the history
    if use_cache:
        logger.info("Skipping the price history for cached data.")
    else:
        with storage.open_db(db_path) as conn:
            storage.record_prices(conn, df_final)

    if make_plots:
        plot_platform_distribution(df_final, output_dir=plots_dir)
        plot_price_analysis(df_final, output_dir=plots_dir)
        plot_price_vs_discount(df_final, output_dir=plots_dir)
        plot_cross_store_prices(store_comparison(matched, sources_in(df_final)), output_dir=plots_dir)
    else:
        logger.info("Skipping plots.")
    logger.info("Pipeline executed successfully!")


def non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return number


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
    parser.add_argument(
        "--output-dir",
        default=".",
        metavar="DIR",
        help="Directory that holds the data/ and plots/ folders. Defaults to the current directory.",
    )
    parser.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="SQLite database to record prices in. Defaults to data/game_prices.db under the output directory.",
    )
    parser.add_argument(
        "--limit",
        type=non_negative_int,
        default=config.DEFAULT_LIMIT,
        metavar="N",
        help=f"Most products to take from each storefront; 0 means everything. Defaults to {config.DEFAULT_LIMIT}.",
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
            output_dir=args.output_dir,
            db_path=args.db,
            limit=args.limit or None,
        )
    except ScrapeError as e:
        logger.error(e)
        return EXIT_SCRAPE_FAILED
    except DataValidationError as e:
        logger.error(e)
        return EXIT_INVALID_DATA
    return 0


if __name__ == "__main__":
    sys.exit(main())
