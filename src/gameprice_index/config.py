"""Site URLs, API parameters and file locations used by the pipeline.

Everything that changes when a storefront is redesigned lives here, so a
broken endpoint is a one-line fix rather than a hunt through the scrapers.
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

# --- Nintendo ---
# the eShop site is a front end over a public Solr search index of the whole catalogue
NINTENDO_SEARCH_URL = "https://searching.nintendo-europe.com/en/select"
NINTENDO_SEARCH_FILTER = "type:GAME AND system_type:nintendoswitch* AND nsuid_txt:*"
NINTENDO_SEARCH_FIELDS = "title,url,nsuid_txt,system_names_txt,price_regular_f,price_lowest_f,price_has_discount_b"
NINTENDO_SEARCH_SORT = "popularity asc"  # most popular first, so a limited run keeps the games people buy
NINTENDO_PAGE_SIZE = 500
NINTENDO_LINK_PREFIX = "https://www.nintendo.com"
# the index can lag behind the shop, so current prices come from the eShop price service
NINTENDO_PRICE_URL = "https://api.ec.nintendo.com/v1/price"
NINTENDO_PRICE_COUNTRY = "GB"
NINTENDO_PRICE_BATCH = 50  # the service rejects requests for more ids than this

# --- PlayStation Direct ---
# the shop front end reads its catalogue from this JSON service
PLAYSTATION_DIRECT_API_URL = (
    "https://api.direct.playstation.com/commercewebservices/ps-direct-gb/products/category/GAMES"
)
PLAYSTATION_DIRECT_LINK_PREFIX = "https://direct.playstation.com"
PLAYSTATION_DIRECT_PAGE_SIZE = 48
PLAYSTATION_DIRECT_MAX_PAGES = 50  # safety stop for the pagination loop

# --- PlayStation Store ---
# the web store talks to a GraphQL service that only accepts queries it knows by hash;
# if Sony ships a new store build the hash below is the thing to update
PLAYSTATION_STORE_API_URL = "https://web.np.playstation.com/api/graphql/v1/op"
PLAYSTATION_STORE_QUERY_HASH = "4ce7d410a4db2c8b635a48c1dcec375906ff63b19dadd87e073f8fd0c0481d35"
PLAYSTATION_STORE_CATEGORY_ID = "4cbf39e2-5749-4970-ba81-93a489e4570c"  # "PS5 games"
PLAYSTATION_STORE_FILTERS = ("storeDisplayClassification:FULL_GAME",)  # no bundles, editions or add-ons
PLAYSTATION_STORE_SORT = "sales30"  # best sellers of the last 30 days first
PLAYSTATION_STORE_LOCALE = "en-GB"
PLAYSTATION_STORE_PAGE_SIZE = 100
PLAYSTATION_STORE_LINK_PREFIX = "https://store.playstation.com/en-gb/product/"

# --- Steam ---
# the search page loads further results from this feed as you scroll
STEAM_SEARCH_URL = "https://store.steampowered.com/search/results/"
STEAM_COUNTRY = "gb"  # prices in pounds
STEAM_CATEGORY_GAMES = 998  # games only: no DLC, software or soundtracks
STEAM_FILTER = "topsellers"
STEAM_PAGE_SIZE = 100

# --- Output locations ---
DATA_DIR = "data"
PLOTS_DIR = "plots"
FINAL_CSV_NAME = "data.csv"
DATABASE_NAME = "game_prices.db"
