"""Finds the same game on different storefronts so prices can be compared like for like.

Stores name things differently ("Marvel’s Wolverine - PS5", "Marvel's Wolverine"),
so titles are first reduced to a comparison key and near-identical keys are then
merged with fuzzy matching.
"""

import logging
import re
import unicodedata

import pandas as pd
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 95  # out of 100; high on purpose, since "construction" and "deconstruction" are different games

# sequels are numbered both ways ("Civilization VII", "Civilization 7"); digits make them comparable
ROMAN_NUMERALS = {
    "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10",
    "xi": "11", "xii": "12", "xiii": "13", "xiv": "14", "xv": "15", "xvi": "16",
}  # fmt: skip

# platform tags that stores add to an otherwise identical title
PLATFORM_TAGS = re.compile(
    r"""
    \s*[-–—:|]?\s*\(?\b(for\s+)?(
        ps4\s*(&|and|/)\s*ps5 | ps5\s*(&|and|/)\s*ps4 | ps5 | ps4 | playstation\s*[45]? |
        xbox\s+series\s+x\s*\|\s*s | xbox\s+series\s+[xs] | xbox\s+one | xbox | windows(\s+10)? |
        nintendo\s+switch(\s+2)?(\s+edition)?
    )\b\)?
    """,
    re.IGNORECASE | re.VERBOSE,
)
FILLER = re.compile(r"\b(standard edition|the)\b")
NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def normalise_title(name: str) -> str:
    """Reduces a store title to a key that is the same wherever the game is sold."""
    # symbols go first: unicode normalisation would otherwise turn "™" into the letters "tm"
    text = name.replace("™", "").replace("®", "").replace("©", "").replace("&", " and ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # "Marvel's", "Marvel’s" and "Marvels" are all the same word
    text = text.replace("'", "").replace("’", "").replace("`", "")
    text = PLATFORM_TAGS.sub(" ", text).lower()
    text = FILLER.sub(" ", text)
    tokens = NOT_ALPHANUMERIC.sub(" ", text).split()
    return " ".join(ROMAN_NUMERALS.get(token, token) for token in tokens)


def _numbers(key: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+", key))


def _same_shape(left: str, right: str) -> bool:
    """Guards against look-alikes: the numbers, the word count and the first letter must all agree."""
    return _numbers(left) == _numbers(right) and len(left.split()) == len(right.split()) and left[0] == right[0]


def merge_similar_keys(keys: list[str], threshold: int = FUZZY_THRESHOLD) -> dict[str, str]:
    """Maps every key to a canonical one, folding near-identical spellings together.

    Look-alikes are kept apart: "nba 2k26" and "nba 2k27" differ in a number, and
    "construction simulator" and "deconstruction simulator" in their first letter.
    """
    canonical: dict[str, str] = {}
    representatives: list[str] = []

    for key in sorted(set(keys), key=lambda k: (len(k), k)):
        match = process.extractOne(key, representatives, scorer=fuzz.ratio, score_cutoff=threshold)
        if match and _same_shape(match[0], key):
            canonical[key] = match[0]
        else:
            canonical[key] = key
            representatives.append(key)
    return canonical


def add_title_keys(df: pd.DataFrame, fuzzy: bool = True) -> pd.DataFrame:
    """Returns a copy of the dataset with a `title_key` column shared by matching games."""
    keyed = df.copy()
    keyed["title_key"] = keyed["name"].map(normalise_title)
    keyed = keyed[keyed["title_key"] != ""]

    if fuzzy and not keyed.empty:
        mapping = merge_similar_keys(keyed["title_key"].tolist())
        keyed["title_key"] = keyed["title_key"].map(mapping)
    return keyed


def cross_store_prices(df: pd.DataFrame, min_stores: int = 2) -> pd.DataFrame:
    """Builds one row per game sold on several storefronts, with a regular-price column per store.

    Regular prices are compared rather than current ones so a sale on one store
    does not masquerade as that store being cheaper.
    """
    keyed = add_title_keys(df.dropna(subset=["price"]))
    keyed["regular_price"] = keyed["price_old"].fillna(keyed["price"])
    # free-to-play titles cost nothing everywhere and would only dilute the comparison
    keyed = keyed[keyed["regular_price"] > 0]

    # a store can list several editions under one key; the cheapest is the base game
    per_store = keyed.sort_values("regular_price").drop_duplicates(subset=["title_key", "source"])
    table = per_store.pivot(index="title_key", columns="source", values="regular_price")
    table = table[table.notna().sum(axis=1) >= min_stores]
    if table.empty:
        return pd.DataFrame(columns=["title_key", "name", "stores", "cheapest_store", "spread"])

    stores = list(table.columns)
    names = per_store.sort_values("name").drop_duplicates("title_key").set_index("title_key")["name"]

    result = table.copy()
    result.insert(0, "name", names.reindex(table.index))
    result["stores"] = table[stores].notna().sum(axis=1)
    result["cheapest_store"] = table[stores].idxmin(axis=1)
    result["spread"] = (table[stores].max(axis=1) - table[stores].min(axis=1)).round(2)
    result = result.sort_values(["stores", "spread", "name"], ascending=[False, False, True]).reset_index()
    result.columns.name = None

    logger.info(f"Matched {len(result)} games sold on at least {min_stores} storefronts.")
    return result


def store_comparison(matched: pd.DataFrame, stores: list[str]) -> pd.DataFrame:
    """Summarises, per storefront, how its prices compare on the games it shares with other stores."""
    rows = []
    for store in stores:
        if store not in matched.columns:
            continue
        shared = matched[matched[store].notna()]
        if shared.empty:
            continue

        other_stores = [other for other in stores if other != store and other in matched.columns]
        elsewhere = shared[other_stores].mean(axis=1)
        lowest = shared[[store, *other_stores]].min(axis=1)
        rows.append(
            {
                "source": store,
                "shared_games": len(shared),
                "median_price": round(float(shared[store].median()), 2),
                "median_price_elsewhere": round(float(elsewhere.median()), 2),
                "mean_difference_pct": round(float(((shared[store] - elsewhere) / elsewhere * 100).mean()), 1),
                # ties count for every store involved, so no store wins just by coming first alphabetically
                "cheapest_share_pct": round(float((shared[store] <= lowest + 0.005).mean() * 100), 1),
            }
        )
    return pd.DataFrame(rows)
