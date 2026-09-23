import argparse
import logging
import os
import sys
from collections.abc import Sequence

import pandas as pd
import requests

from gameprice_index import alerts, config, storage
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
    db_path = db_path or default_db_path(output_dir)

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
    # read-only commands over the recorded history; without one the pipeline runs
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", title="history commands")

    deals = commands.add_parser("deals", help="List games on sale right now, deepest discount first.")
    drops = commands.add_parser("drops", help="List games whose price fell since the previous scrape.")
    history = commands.add_parser("history", help="Show every recorded price of one product.")
    history.add_argument("product_code", help="The store's id for the product, as shown by the other commands.")

    alert = commands.add_parser("alerts", help="Report watchlist games that hit a target price or a new low.")
    alert.add_argument("--watchlist", default=config.WATCHLIST_NAME, metavar="PATH", help="Watchlist TOML file.")
    alert.add_argument("--dry-run", action="store_true", help="Show the alerts without sending or recording them.")

    serve = commands.add_parser("serve", help="Serve the price history as an HTTP API (needs the api extra).")
    serve.add_argument("--host", default="127.0.0.1", help="Address to listen on. Defaults to this machine only.")
    serve.add_argument("--port", type=int, default=8000, help="Port to listen on.")

    for command in (deals, drops, history, alert, serve):
        command.add_argument("--db", default=None, metavar="PATH", help="SQLite database to read.")
    for command in (deals, drops):
        command.add_argument("--top", type=non_negative_int, default=20, metavar="N", help="Rows to show.")
    return parser


def default_db_path(output_dir: str = ".") -> str:
    return os.path.join(output_dir, config.DATA_DIR, config.DATABASE_NAME)


def run_query(command: str, args: argparse.Namespace) -> int:
    """Prints the result of one history command and returns the exit code."""
    db_path = args.db or default_db_path()
    if not os.path.exists(db_path):
        logger.error(f"No price history at {db_path}; run the pipeline first or pass --db.")
        return EXIT_SCRAPE_FAILED

    if command == "alerts":
        return run_alerts_command(db_path, args)
    if command == "serve":
        return run_server(db_path, args.host, args.port)

    with storage.open_db(db_path) as conn:
        if command == "deals":
            columns = ["source", "name", "price", "price_old", "discount_pct", "product_code"]
            table = storage.current_deals(conn, limit=args.top or None)[columns]
        elif command == "drops":
            columns = ["source", "name", "previous_price", "price", "drop_pct", "scrape_date", "product_code"]
            drops = storage.price_drops(conn)
            table = (drops.head(args.top) if args.top else drops)[columns]
        else:
            table = storage.price_history(conn, args.product_code)

    if table.empty:
        print("Nothing to show.")
    else:
        print(table.to_string(index=False))
    return 0


def run_server(db_path: str, host: str, port: int) -> int:
    """Starts the HTTP API; the web stack is imported here so the pipeline does not depend on it."""
    try:
        import uvicorn

        from gameprice_index.api import create_app
    except ImportError:
        logger.error("The API needs extra packages; install them with: uv sync --extra api")
        return EXIT_SCRAPE_FAILED

    uvicorn.run(create_app(db_path), host=host, port=port)
    return 0


def run_alerts_command(db_path: str, args: argparse.Namespace) -> int:
    """Prints new watchlist alerts and, unless it is a dry run, sends and records them."""
    webhook_url = os.environ.get(config.DISCORD_WEBHOOK_ENV)
    try:
        found = alerts.run_alerts(db_path, args.watchlist, webhook_url=webhook_url, dry_run=args.dry_run)
    except alerts.WatchlistError as e:
        logger.error(e)
        return EXIT_INVALID_DATA
    except requests.RequestException as e:
        logger.error(f"Could not deliver the alerts: {e}")
        return EXIT_SCRAPE_FAILED

    if not found:
        print("No new alerts.")
    for alert in found:
        print(alert.message())
    if found and not args.dry_run and not webhook_url:
        logger.info(f"Set {config.DISCORD_WEBHOOK_ENV} to also post alerts to Discord.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Console entry point; returns the process exit code."""
    args = build_parser().parse_args(argv)

    configure_logging()
    if args.command:
        return run_query(args.command, args)

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
