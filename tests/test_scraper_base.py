import pytest

from gameprice_index.scrapers import RECORD_FIELDS, SCRAPERS, ScrapeError, Scraper, get_scraper


class StubScraper(Scraper):
    name = "stub"
    source = "Stub Store"

    def __init__(self, records=None, error=None, **kwargs):
        super().__init__(**kwargs)
        self._records = records or []
        self._error = error

    def fetch_records(self):
        if self._error:
            raise self._error
        return [self.record(**fields) for fields in self._records]


def test_record_fills_every_field():
    record = StubScraper().record(name="Mario Kart World", price=66.99)

    assert tuple(record) == RECORD_FIELDS
    assert record["source"] == "Stub Store"
    assert record["name"] == "Mario Kart World"
    assert record["badge"] is None


def test_record_rejects_unknown_fields():
    with pytest.raises(KeyError):
        StubScraper().record(title="Mario Kart World")


def test_scrape_returns_records():
    scraper = StubScraper(records=[{"name": "A", "product_code": "1"}, {"name": "B", "product_code": "2"}])

    assert [record["name"] for record in scraper.scrape()] == ["A", "B"]


def test_scrape_applies_limit():
    scraper = StubScraper(records=[{"name": "A"}, {"name": "B"}, {"name": "C"}], limit=2)

    assert len(scraper.scrape()) == 2


def test_scrape_wraps_failures():
    """Any failure must stop the pipeline instead of producing an empty dataset."""
    scraper = StubScraper(error=ConnectionError("boom"))

    with pytest.raises(ScrapeError, match="Failed to scrape Stub Store: boom"):
        scraper.scrape()


def test_scrape_raises_when_nothing_is_found():
    with pytest.raises(ScrapeError, match="No Stub Store games found"):
        StubScraper().scrape()


def test_registry_lookup():
    assert get_scraper("nintendo").source == "Nintendo"
    assert set(SCRAPERS) >= {"nintendo", "playstation-direct"}

    with pytest.raises(ValueError, match="Unknown source 'sega'"):
        get_scraper("sega")


@pytest.mark.parametrize("name", sorted(SCRAPERS))
def test_registered_scrapers_follow_the_contract(name):
    scraper = SCRAPERS[name]

    assert issubclass(scraper, Scraper)
    assert scraper.name == name
    assert scraper.source
