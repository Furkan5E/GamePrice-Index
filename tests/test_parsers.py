"""Parser tests against trimmed copies of the real storefront pages."""

from gameprice_index.scraper import parse_nintendo_listing, parse_nintendo_prices, parse_playstation_tiles


def test_parse_nintendo_listing(load_fixture):
    games = parse_nintendo_listing(load_fixture("nintendo_listing.html"))

    assert len(games) == 5
    assert games[0] == {
        "name": "Star Fox",
        "platform": "Nintendo Switch 2",
        "url": "https://www.nintendo.co.uk/en-gb/Games/Nintendo-Switch-2-games/Star-Fox-3094728.html",
        "nsuid": "70010000123168",
        "price": None,
        "price_old": None,
        "badge": None,
        "date_range": None,
        "product_code": None,
        "out_of_stock": None,
        "source": "Nintendo",
    }
    # the static page has empty price placeholders, so no game is priced yet
    assert all(game["price"] is None for game in games)


def test_parse_nintendo_listing_keeps_multi_edition_nsuids(load_fixture):
    """Games sold in several editions list every nsuid, separated by a pipe."""
    games = parse_nintendo_listing(load_fixture("nintendo_listing.html"))

    assert games[1]["nsuid"] == "70010000115568|70050000069174"
    assert games[1]["name"].startswith("Super Mario Bros. Wonder – Nintendo Switch 2 Edition")


def test_parse_nintendo_prices(load_fixture):
    prices = parse_nintendo_prices(load_fixture("nintendo_listing_rendered.html"))

    assert prices[0] == {"nsuid": "70010000123168", "price": "£41.99", "price_old": None}
    assert all(price["price"] for price in prices)


def test_parse_nintendo_prices_on_sale(load_fixture):
    """Regression: the sale price is the current price and the struck-through one is the old price."""
    prices = parse_nintendo_prices(load_fixture("nintendo_listing_rendered.html"))
    on_sale = [price for price in prices if price["price_old"]]

    assert on_sale == [
        {"nsuid": "70010000101676|70070000031399", "price": "£40.29", "price_old": "£64.99"},
        {"nsuid": "70010000126200", "price": "£2.99", "price_old": "£5.39"},
    ]


def test_parse_playstation_direct_listing(load_fixture):
    tiles = parse_playstation_tiles(load_fixture("playstation_direct_listing.html"))

    assert [tile["product_code"] for tile in tiles] == [
        "1000057436-GB",
        "1000049375-GB",
        "1000048721-GB",
        "1000039370-GB",
    ]
    assert tiles[0]["name"] == "Marvel’s Wolverine - PS5"
    assert tiles[0]["price"] == "£69.99"
    assert tiles[0]["price_old"] is None
    assert tiles[0]["url"] == "https://direct.playstation.com/en-gb/buy-games/marvels-wolverine-ps5"
    assert tiles[1]["badge"] == "EXCLUSIVE"
    assert not any(tile["out_of_stock"] for tile in tiles)
