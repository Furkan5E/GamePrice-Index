import pandas as pd
import pytest

from gameprice_index.matching import (
    add_title_keys,
    cross_store_prices,
    merge_similar_keys,
    normalise_title,
    store_comparison,
)
from gameprice_index.processor import build_frame


@pytest.mark.parametrize(
    ("title", "key"),
    [
        ("Marvel’s Wolverine - PS5", "marvels wolverine"),
        ("Marvel's Wolverine", "marvels wolverine"),
        ("Sid Meier’s Civilization® VII", "sid meiers civilization 7"),
        ("Grand Theft Auto V (Xbox One)", "grand theft auto 5"),
        ("Mafia III: Definitive Edition for PS5®", "mafia 3 definitive edition"),
        ("The Witcher 3: Wild Hunt for Nintendo Switch", "witcher 3 wild hunt"),
        ("Monster Hunter World™", "monster hunter world"),
        ("Pokémon Legends: Z-A", "pokemon legends z a"),
        ("Hogwarts Legacy PS4 & PS5", "hogwarts legacy"),
        ("EA SPORTS FC™ 27 Standard Edition", "ea sports fc 27"),
        ("PC Building Simulator", "pc building simulator"),
        ("™®", ""),
    ],
)
def test_normalise_title(title, key):
    assert normalise_title(title) == key


def test_trademark_symbols_do_not_become_letters():
    """Regression: unicode normalisation turned "World™" into "worldtm", which then matched nothing."""
    assert normalise_title("LEGO® Jurassic World™") == "lego jurassic world"


def test_merge_similar_keys_folds_near_identical_spellings():
    mapping = merge_similar_keys(["assassins creed shadows", "assassins creed shadow", "hades"])

    assert mapping["assassins creed shadows"] == mapping["assassins creed shadow"]
    assert mapping["hades"] == "hades"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("nba 2k26", "nba 2k27"),  # a different year
        ("little nightmares 2", "little nightmares 3"),  # a sequel
        ("construction simulator", "deconstruction simulator"),  # a different game
        ("far lands", "farlands"),  # a different word count
        ("hades", "halo"),
    ],
)
def test_merge_similar_keys_keeps_lookalikes_apart(left, right):
    mapping = merge_similar_keys([left, right])

    assert mapping[left] != mapping[right]


def _dataset() -> pd.DataFrame:
    def row(source, code, name, price, price_old=None):
        return {
            "source": source,
            "platform": source,
            "product_code": code,
            "name": name,
            "price": price,
            "price_old": price_old,
            "badge": None,
            "out_of_stock": None,
            "url": None,
        }

    return build_frame(
        [
            row("Steam", "s1", "Hogwarts Legacy", 12.49, 49.99),
            row("PlayStation Store", "p1", "Hogwarts Legacy PS5", 59.99),
            row("Nintendo", "n1", "Hogwarts Legacy", 49.99),
            row("Nintendo", "n1d", "Hogwarts Legacy", 64.99),  # a second, dearer edition under the same name
            row("Steam", "s2", "Hades II", 24.99),
            row("Nintendo", "n2", "Hades 2", 24.99),
            row("Steam", "s3", "Dota 2", 0.0),
            row("Xbox", "x3", "Dota 2", 0.0),
            row("Steam", "s4", "Only On Steam", 9.99),
            row("Xbox", "x5", "Unpriced Game", None),
            row("Steam", "s5", "Unpriced Game", 5.0),
        ]
    )


def test_add_title_keys_links_the_same_game_across_stores():
    keyed = add_title_keys(_dataset())

    assert keyed[keyed["name"].str.startswith("Hogwarts")]["title_key"].nunique() == 1
    assert keyed[keyed["name"].str.startswith("Hades")]["title_key"].unique().tolist() == ["hades 2"]


def test_cross_store_prices_compares_regular_prices():
    """A sale on one store must not make it look cheaper: Steam's regular price is 49.99, not 12.49."""
    matched = cross_store_prices(_dataset()).set_index("title_key")
    hogwarts = matched.loc["hogwarts legacy"]

    assert hogwarts["Steam"] == 49.99
    assert hogwarts["PlayStation Store"] == 59.99
    assert hogwarts["Nintendo"] == 49.99  # the cheaper of the two Nintendo editions
    assert hogwarts["stores"] == 3
    assert hogwarts["spread"] == 10.0


def test_cross_store_prices_only_keeps_games_that_can_be_compared():
    matched = cross_store_prices(_dataset())

    # no single-store games, no free-to-play titles, no games priced on just one store
    assert sorted(matched["title_key"]) == ["hades 2", "hogwarts legacy"]
    assert matched.iloc[0]["title_key"] == "hogwarts legacy"  # most stores first


def test_cross_store_prices_with_nothing_in_common():
    matched = cross_store_prices(_dataset().query("source == 'Steam'"))

    assert matched.empty
    assert "cheapest_store" in matched.columns


def test_store_comparison_counts_ties_for_every_store():
    matched = cross_store_prices(_dataset())
    summary = store_comparison(matched, ["Nintendo", "PlayStation Store", "Steam", "Xbox"]).set_index("source")

    assert summary.index.tolist() == ["Nintendo", "PlayStation Store", "Steam"]
    assert summary.loc["Steam", "shared_games"] == 2
    assert summary.loc["Steam", "cheapest_share_pct"] == 100.0
    assert summary.loc["Nintendo", "cheapest_share_pct"] == 100.0  # tied with Steam on both games
    assert summary.loc["PlayStation Store", "cheapest_share_pct"] == 0.0
    assert summary.loc["PlayStation Store", "mean_difference_pct"] == 20.0


def test_store_comparison_with_no_shared_games_keeps_its_columns():
    """Regression: an empty comparison had no columns and crashed the plot that reads it."""
    matched = cross_store_prices(_dataset().query("source == 'Steam'"))

    summary = store_comparison(matched, ["Steam", "Xbox"])

    assert summary.empty
    assert "shared_games" in summary.columns
