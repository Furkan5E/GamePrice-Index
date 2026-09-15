from pathlib import Path

import pytest

from gameprice_index import config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    """Returns a function that reads a saved page from tests/fixtures."""

    def _load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture(autouse=True)
def no_request_delay(monkeypatch):
    """Tests never hit a real site, so there is nobody to be polite to."""
    monkeypatch.setattr(config, "REQUEST_DELAY", 0)
