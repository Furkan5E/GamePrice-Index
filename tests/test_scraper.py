from bs4 import BeautifulSoup
from src.scraper import parse_nintendo_price

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
