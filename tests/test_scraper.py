import requests
from bs4 import BeautifulSoup
from src.scraper import parse_nintendo_price, scrape_nintendo_base

NINTENDO_LISTING = """
<ul>
  <li class="page-list-group-item" data-nsuid="70010000118193">
    <a href="/en-gb/Games/Emoji-Killer-3174797.html">
      <p class="page-title">Emoji Killer – Casino Massacre</p>
      <p class="page-data">
        Nintendo Switch
      </p>
    </a>
  </li>
</ul>
"""

def _fake_response(html: str) -> requests.Response:
    """Builds a response the way the site sends it: utf-8 bytes, no charset header."""
    response = requests.Response()
    response.status_code = 200
    response._content = html.encode("utf-8")
    response.encoding = "ISO-8859-1"
    return response

def _price_container(html: str):
    return BeautifulSoup(html, "html.parser").find("p", class_="price-small")

def test_parse_nintendo_price_regular():
    """A game that is not on sale has a price and no old price."""
    container = _price_container(
        '<p class="price-small"><span data-price="">£41.99</span>'
        '<span class="discount" data-discount=""></span></p>'
    )
    assert parse_nintendo_price(container) == ("£41.99", None)

def test_parse_nintendo_price_on_sale():
    """The discount span holds the sale price, data-price the original one."""
    container = _price_container(
        '<p class="price-small"><span class="original-price" data-price="">£8.99</span>'
        '<span class="discount" data-discount="">£7.64*</span></p>'
    )
    assert parse_nintendo_price(container) == ("£7.64", "£8.99")

def test_parse_nintendo_price_missing():
    assert parse_nintendo_price(None) == (None, None)

def test_scrape_nintendo_base_decodes_utf8(monkeypatch):
    """Regression: names with non-ascii punctuation used to come back as mojibake."""
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _fake_response(NINTENDO_LISTING))

    games = scrape_nintendo_base("https://example.test/games")

    assert len(games) == 1
    assert games[0]["name"] == "Emoji Killer – Casino Massacre"
    assert games[0]["platform"] == "Nintendo Switch"
