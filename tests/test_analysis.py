import pandas as pd
import pytest

from gameprice_index import cli
from gameprice_index.analysis import build_report, platform_summary, storefront_summary
from gameprice_index.processor import build_frame


def _dataset() -> pd.DataFrame:
    """Thirty games on each of two stores; Steam is 10% cheaper and discounts every third game."""
    records = []
    for n in range(1, 31):
        base = 10.0 * n
        records.append(
            {
                "source": "Nintendo",
                "platform": "Nintendo Switch",
                "product_code": f"n{n}",
                "name": f"Shared Game {n}",
                "price": base,
            }
        )
        steam_regular = round(base * 0.9, 2)
        records.append(
            {
                "source": "Steam",
                "platform": "PC",
                "product_code": f"s{n}",
                "name": f"Shared Game {n}",
                "price": steam_regular / 2 if n % 3 == 0 else steam_regular,
                "price_old": steam_regular if n % 3 == 0 else None,
            }
        )
    records.append({"source": "Steam", "platform": "PC", "product_code": "free", "name": "Free Game", "price": 0.0})
    records.append(
        {"source": "PlayStation Direct", "platform": "PS5", "product_code": "p1", "name": "Collector", "price": 219.99}
    )
    return build_frame(records)


def test_storefront_summary():
    summary = storefront_summary(_dataset()).set_index("source")

    assert summary.loc["Nintendo", "games"] == 30
    assert summary.loc["Nintendo", "median_price"] == 155.0
    assert summary.loc["Nintendo", "on_sale_pct"] == 0.0
    assert pd.isna(summary.loc["Nintendo", "median_discount_pct"])
    assert summary.loc["Steam", "games"] == 31
    assert summary.loc["Steam", "on_sale_pct"] == 32.3
    assert summary.loc["Steam", "median_discount_pct"] == 50.0
    assert summary.loc["Steam", "free_pct"] == 3.2


def test_storefront_summary_with_an_unpriced_store():
    df = build_frame([{"source": "Xbox", "product_code": "x", "name": "Unpriced", "price": None}])

    row = storefront_summary(df).iloc[0]

    assert row["games"] == 1
    assert pd.isna(row["median_price"])


def test_platform_summary_skips_small_platforms():
    platforms = platform_summary(_dataset())

    assert platforms["platform"].tolist() == ["Nintendo Switch", "PC"]


def test_report_states_what_the_data_shows():
    report = build_report(_dataset())

    assert report.startswith("# Findings")
    assert "62 games from 3 UK storefronts." in report
    assert "**Steam** has the lowest median price" in report
    assert "**Steam** has the largest share of its catalogue on sale (32.3%)" in report
    assert "PlayStation Direct lists fewer than 20 games" in report
    assert "30 games were matched on at least two storefronts" in report
    # regular prices are compared, so Steam is 10% cheaper however many of its games are on sale
    assert "**Steam** averages -10%" in report
    assert "**Nintendo** +11.1%" in report


def test_report_tables_are_valid_markdown():
    report = build_report(_dataset())
    table_lines = [line for line in report.splitlines() if line.startswith("|")]

    assert table_lines
    assert all(line.endswith("|") for line in table_lines)
    assert "nan" not in report.lower().replace("financ", "")


def test_gap_table_leaves_out_stores_without_any_of_the_games():
    report = build_report(_dataset())
    gap_header = next(line for line in report.splitlines() if line.startswith("| Game |"))

    assert gap_header == "| Game | Nintendo | Steam | Gap (£) |"


def test_report_for_a_single_store():
    report = build_report(_dataset().query("source == 'Nintendo'"))

    assert "No game is sold on more than one of the scraped storefronts." in report


def test_report_command_writes_the_file(tmp_path):
    data = tmp_path / "data.csv"
    _dataset().to_csv(data, index=False)
    output = tmp_path / "reports" / "findings.md"

    assert cli.main(["report", "--data", str(data), "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8").startswith("# Findings")


@pytest.mark.parametrize("content", [None, "source,name\nNintendo,Broken\n"])
def test_report_command_rejects_missing_or_invalid_data(tmp_path, content):
    data = tmp_path / "data.csv"
    if content:
        data.write_text(content, encoding="utf-8")

    assert cli.main(["report", "--data", str(data), "--output", str(tmp_path / "out.md")]) == 2
    assert not (tmp_path / "out.md").exists()
