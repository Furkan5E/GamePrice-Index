"""Site URLs, API parameters, CSS selectors and file locations used by the pipeline.

Everything that changes when a storefront is redesigned lives here, so a
broken endpoint or selector is a one-line fix rather than a hunt through the scrapers.
"""

# --- HTTP ---
REQUEST_TIMEOUT = 30  # seconds
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}
REQUEST_RETRIES = 3
REQUEST_BACKOFF = 1.0  # seconds; doubles after every failed attempt
REQUEST_RETRY_STATUSES = (429, 500, 502, 503, 504)
REQUEST_DELAY = 0.25  # seconds between requests to the same site

# --- Scraping ---
DEFAULT_LIMIT = 1000  # products per storefront unless --limit says otherwise

# --- Selenium ---
SELENIUM_WAIT = 15  # seconds to wait for dynamic content before giving up

# --- Nintendo ---
# the eShop site is a front end over a public Solr search index of the whole catalogue
NINTENDO_SEARCH_URL = "https://searching.nintendo-europe.com/en/select"
NINTENDO_SEARCH_FILTER = "type:GAME AND system_type:nintendoswitch* AND nsuid_txt:*"
NINTENDO_SEARCH_FIELDS = "title,url,nsuid_txt,system_names_txt,price_regular_f,price_lowest_f,price_has_discount_b"
NINTENDO_SEARCH_SORT = "popularity asc"  # most popular first, so a limited run keeps the games people buy
NINTENDO_PAGE_SIZE = 500
NINTENDO_LINK_PREFIX = "https://www.nintendo.com"

# --- PlayStation Direct ---
PLAYSTATION_URL = "https://direct.playstation.com/en-gb/games/"
PLAYSTATION_MAX_PAGES = 50  # safety stop for the pagination loop
PLAYSTATION_SELECTORS = {
    "tile": ".products-list-section .product-tile",
    "any_tile": ".product-tile",
    "name": "p.product-card-details__name",
    "link": ".product-card-image .product-tile__full-width a",
    "prices": "div.product-card-details__price .text-product-price span.price-whole-text",
    "badge": "div.badge .badge-label",
    "out_of_stock": "p.out-stock-wrpr",
    "product_code": "button[data-product-code]",
    "next_button": "button.desktop-pagination__button.right-chevron-blue",
}

# --- Output locations ---
DATA_DIR = "data"
PLOTS_DIR = "plots"
FINAL_CSV_NAME = "data.csv"
DATABASE_NAME = "game_prices.db"
