# GamePrice-Index

![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![Build](https://img.shields.io/badge/Build-uv-purple.svg)
![Selenium](https://img.shields.io/badge/Selenium-Supported-43B02A.svg?logo=selenium)
![Pandas](https://img.shields.io/badge/Pandas-Data%20ETL-150458.svg?logo=pandas)
![License](https://img.shields.io/badge/License-MIT-blue.svg)

An automated ETL (Extract, Transform, Load) and market intelligence pipeline that scrapes, normalises, and analyses dynamic video game pricing across Nintendo eShop and PlayStation Direct platforms.

---

## Features

* **Hybrid Scraping Architecture:** Combines fast static HTML parsing via `requests` and `BeautifulSoup` with headless `selenium` automation to handle dynamic JavaScript price rendering and pagination.
* **Automated Data Cleaning & ETL:** Cleans currency symbols, standardises product identifiers (`nsuid`, `product_code`), handles encoding quirks, and calculates pricing differentials via `pandas`.
* **Data Visualisation:** Generates analytical scatter and bar plots comparing pricing and discount behaviours across platforms using `matplotlib`.
* **Offline Caching:** Supports cached execution modes (`--cached`) to enable instant data processing and visualisation without re-triggering network requests.
* **Robust Logging:** Integrated Python `logging` to provide clear, real-time pipeline execution tracking.

---

## Setup Instructions

Clone the repository and install dependencies using uv:
```bash
git clone https://github.com/Furkan5E/GamePrice-Index.git
cd GamePrice-Index
uv sync
```
Run the live scraping pipeline:
```bash
uv run python -m src.main
```
Run using cached local datasets:
```bash
uv run python -m src.main --cached
```
---
## Analytics & Visualisations

### Price Distribution & Ranked Index
![Price Analysis](plots/price_analysis.png)

---
## Disclaimer

This tool was developed for educational and portfolio demonstration purposes only. All scraped data is the property of its respective platform holders.
