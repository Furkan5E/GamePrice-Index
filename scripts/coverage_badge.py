"""Renders a coverage badge SVG from a coverage.xml report.

Usage: python scripts/coverage_badge.py coverage.xml badge/coverage.svg
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# (minimum percentage, colour) pairs, checked from the top down
COLOURS = [(90, "#4c1"), (80, "#97ca00"), (70, "#a4a61d"), (60, "#dfb317"), (0, "#e05d44")]

TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="104" height="20" role="img" aria-label="coverage: {pct}%">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="104" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="63" height="20" fill="#555"/>
    <rect x="63" width="41" height="20" fill="{colour}"/>
    <rect width="104" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="31.5" y="14">coverage</text>
    <text x="83.5" y="14">{pct}%</text>
  </g>
</svg>
"""


def read_percentage(report_path: str) -> int:
    """Returns the line coverage recorded in a Cobertura-style coverage.xml."""
    root = ET.parse(report_path).getroot()
    return round(float(root.attrib["line-rate"]) * 100)


def render_badge(pct: int) -> str:
    colour = next(colour for minimum, colour in COLOURS if pct >= minimum)
    return TEMPLATE.format(pct=pct, colour=colour)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2

    pct = read_percentage(argv[1])
    output = Path(argv[2])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_badge(pct), encoding="utf-8")
    print(f"Coverage {pct}% -> {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
