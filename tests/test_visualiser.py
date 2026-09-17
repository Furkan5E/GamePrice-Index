import pandas as pd
import pytest

from gameprice_index import visualiser
from gameprice_index.processor import build_frame

PLOTS = [
    (visualiser.plot_platform_distribution, "platform_distribution.png"),
    (visualiser.plot_price_analysis, "price_analysis.png"),
    (visualiser.plot_price_vs_discount, "price_vs_discount.png"),
]


def _dataset(sources) -> pd.DataFrame:
    records = []
    for source in sources:
        for n in range(1, 41):
            records.append(
                {
                    "source": source,
                    "platform": f"{source} console",
                    "product_code": f"{source}-{n}",
                    "name": f"Game {n}",
                    "price": n * 1.5,
                    "price_old": n * 3.0 if n % 4 == 0 else None,
                    "badge": None,
                    "out_of_stock": None,
                    "url": None,
                }
            )
    return build_frame(records)


@pytest.mark.parametrize(("plot", "filename"), PLOTS)
def test_plots_handle_any_number_of_sources(tmp_path, plot, filename):
    df = _dataset(["Nintendo", "PlayStation Store", "Steam", "Xbox", "A New Store"])

    path = plot(df, output_dir=str(tmp_path))

    assert path.endswith(filename)
    assert (tmp_path / filename).stat().st_size > 5_000


@pytest.mark.parametrize(("plot", "filename"), PLOTS)
def test_plots_handle_a_single_small_source(tmp_path, plot, filename):
    df = _dataset(["Nintendo"]).head(3)

    plot(df, output_dir=str(tmp_path))

    assert (tmp_path / filename).exists()


def test_discount_plot_without_any_deals(tmp_path):
    df = _dataset(["Nintendo"])
    df[["price_old", "discount_amount", "discount_pct"]] = None

    visualiser.plot_price_vs_discount(df, output_dir=str(tmp_path))

    assert (tmp_path / "price_vs_discount.png").exists()


def test_sources_keep_a_fixed_colour_order():
    df = pd.DataFrame({"source": ["Xbox", "Zeta Store", "Nintendo", "Steam"]})

    assert visualiser.sources_in(df) == ["Nintendo", "Steam", "Xbox", "Zeta Store"]
    assert visualiser.colour_for("Nintendo") == visualiser.SOURCE_COLOURS["Nintendo"]
    assert visualiser.colour_for("Zeta Store") == visualiser.FALLBACK_COLOUR


def test_tiny_catalogues_are_left_out_of_the_distribution(tmp_path, monkeypatch):
    """Four collector's editions used to draw as a 100% spike that hid every other store."""
    df = pd.concat([_dataset(["Nintendo", "Steam"]), _dataset(["PlayStation Direct"]).head(4)])
    plotted = []
    monkeypatch.setattr(visualiser, "colour_for", lambda source: plotted.append(source) or "#000000")

    visualiser.plot_price_analysis(df, output_dir=str(tmp_path))

    assert set(plotted) == {"Nintendo", "Steam"}


def test_a_lone_tiny_catalogue_is_still_plotted(tmp_path, monkeypatch):
    plotted = []
    monkeypatch.setattr(visualiser, "colour_for", lambda source: plotted.append(source) or "#000000")

    visualiser.plot_price_analysis(_dataset(["PlayStation Direct"]).head(4), output_dir=str(tmp_path))

    assert plotted == ["PlayStation Direct"]
