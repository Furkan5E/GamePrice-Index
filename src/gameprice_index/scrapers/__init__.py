"""Storefront scrapers, looked up by the name used on the command line."""

from gameprice_index.scrapers.base import RECORD_FIELDS, ScrapeError, Scraper
from gameprice_index.scrapers.nintendo import NintendoScraper
from gameprice_index.scrapers.playstation import PlayStationScraper

SCRAPERS: dict[str, type[Scraper]] = {
    scraper.name: scraper
    for scraper in (
        NintendoScraper,
        PlayStationScraper,
    )
}


def get_scraper(name: str) -> type[Scraper]:
    """Returns the scraper class registered under a name."""
    try:
        return SCRAPERS[name]
    except KeyError:
        raise ValueError(f"Unknown source '{name}'; choose from {', '.join(SCRAPERS)}") from None


__all__ = ["RECORD_FIELDS", "SCRAPERS", "ScrapeError", "Scraper", "get_scraper"]
