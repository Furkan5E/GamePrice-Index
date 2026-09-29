"""The package must be runnable as `python -m gameprice_index` and as the installed script."""

import subprocess
import sys

import gameprice_index


def test_module_entry_point_shows_help():
    result = subprocess.run(
        [sys.executable, "-m", "gameprice_index", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0
    assert "usage: gameprice-index" in result.stdout
    for command in ("deals", "drops", "history", "alerts", "report", "serve", "dashboard"):
        assert command in result.stdout


def test_module_entry_point_propagates_the_exit_code(tmp_path):
    """A failing command must fail the process, or cron and CI would never notice."""
    result = subprocess.run(
        [sys.executable, "-m", "gameprice_index", "deals", "--db", str(tmp_path / "missing.db")],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 1
    assert "No price history" in result.stderr


def test_version_is_exposed():
    assert gameprice_index.__version__.count(".") == 2
