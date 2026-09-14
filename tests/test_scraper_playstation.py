from gameprice_index.scrapers.playstation import parse_playstation_tiles

PLAYSTATION_LISTING = """
<div class="products-list-section">
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


def test_parse_playstation_tile_on_sale_and_out_of_stock():
    tile = parse_playstation_tiles(PLAYSTATION_LISTING)[0]

    assert tile["price"] == "£39.99"
    assert tile["price_old"] == "£59.99"
    assert tile["out_of_stock"] is True
    assert tile["badge"] is None
