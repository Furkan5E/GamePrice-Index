import pytest
import requests
from bs4 import BeautifulSoup
from gameprice_index.scraper import (
    ScrapeError,
    parse_nintendo_price,
    parse_playstation_tiles,
    scrape_nintendo_base
)

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

def test_scrape_nintendo_base_sends_timeout_and_user_agent(monkeypatch):
    """A request without a timeout can hang the whole pipeline."""
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return _fake_response(NINTENDO_LISTING)

    monkeypatch.setattr(requests, "get", fake_get)
    scrape_nintendo_base("https://example.test/games")

    assert seen["timeout"] > 0
    assert "User-Agent" in seen["headers"]

def test_scrape_nintendo_base_raises_on_network_error(monkeypatch):
    """A failed request must stop the pipeline instead of producing an empty dataset."""
    def fake_get(url, **kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(ScrapeError):
        scrape_nintendo_base("https://example.test/games")

def test_scrape_nintendo_base_raises_when_no_games_found(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _fake_response("<html></html>"))

    with pytest.raises(ScrapeError):
        scrape_nintendo_base("https://example.test/games")

PLAYSTATION_LISTING = """
<div class="products-list-section">
  <div class="product-tile">
    <div class="badge"><span class="badge-label">PRE-ORDER</span></div>
    <div class="product-card-image">
      <div class="product-tile__full-width"><a href="https://direct.playstation.com/en-gb/buy-games/wolverine"></a></div>
    </div>
    <p class="product-card-details__name"> Marvel's Wolverine - PS5 </p>
    <div class="product-card-details__price">
      <div class="text-product-price"><span class="price-whole-text">£69.99</span></div>
    </div>
    <button data-product-code="1000057436-GB"></button>
  </div>
  <div class="product-tile">
    <p class="product-card-details__name">Astro Bot - PS5</p>
    <div class="product-card-details__price">
      <div class="text-product-price">
        <span class="price-whole-text">£39.99</span><span class="price-whole-text">£59.99</span>
      </div>
    </div>
    <p class="out-stock-wrpr">Out of stock</p>
    <button data-product-code="1000044444-GB"></button>
  </div>
</div>
"""

def test_parse_playstation_tiles():
    tiles = parse_playstation_tiles(PLAYSTATION_LISTING)

    assert [t["product_code"] for t in tiles] == ["1000057436-GB", "1000044444-GB"]
    assert tiles[0]["name"] == "Marvel's Wolverine - PS5"
    assert tiles[0]["badge"] == "PRE-ORDER"
    assert tiles[0]["price"] == "£69.99"
    assert tiles[0]["price_old"] is None
    assert tiles[0]["out_of_stock"] is False
    assert tiles[1]["price"] == "£39.99"
    assert tiles[1]["price_old"] == "£59.99"
    assert tiles[1]["out_of_stock"] is True
