# Inaproc Market Survey Tool

A Streamlit-based tool for Indonesian government procurement officers to scrape and analyze product prices from the national e-catalog portal ([katalog.inaproc.id](https://katalog.inaproc.id)).

Market price surveys (*survei harga pasar*) are a **mandatory step** in every government procurement process under Indonesian law (Perpres 16/2018 jo. 12/2021). This tool automates that process — reducing hours of manual work to minutes.

## Features

- **Single & Batch Search** — search one item or upload a list for bulk survey
- **Two scraping modes:**
  - **API mode** (fast) — intercepts the katalog.inaproc.id search API via Chrome CDP; requires an active logged-in browser session
  - **Playwright mode** (thorough) — full browser automation with product screenshots
- **Price filtering** — min/max price range with Indonesian Rupiah format support
- **Location filter** — restrict results to specific regions (e.g., Kalimantan Selatan)
- **Sort options** — by price, relevance, or seller rating
- **Excel export** — results exported to `.xlsx` with all product details
- **Screenshot capture** — saves product page screenshots per item (Playwright mode)

## Use Case

Designed for Indonesian government procurement working groups (*Kelompok Kerja / Pokja*) who need to:
1. Survey market prices for budget estimation (*HPS — Harga Perkiraan Sendiri*)
2. Document price references for procurement compliance
3. Compare prices across multiple vendors on the national e-catalog

## Requirements

- Python 3.10+
- Google Chrome (for CDP/API mode)
- Dependencies: `streamlit`, `playwright`, `pandas`, `openpyxl`

```bash
pip install -r requirements.txt
playwright install chromium
```

## Running

```bash
# Windows (portable launcher)
portable_launcher.bat

# Or directly
streamlit run app.py
```

App runs on `http://localhost:8511` by default.

## Setup (first time)

```bash
# Install dependencies
setup_komputer_baru.bat

# Or manually
pip install -r requirements.txt
playwright install
```

For API mode: open Chrome, log in to [katalog.inaproc.id](https://katalog.inaproc.id), then run the tool. The scraper intercepts the active session via Chrome DevTools Protocol (CDP).

## Output

Results are exported as `.xlsx` files containing:
- Product name, brand, specification
- Price (unit & total)
- Vendor/seller name
- Location
- Source URL

## Context

This tool is part of a broader open-source procurement automation toolkit for Indonesian government agencies. Indonesia's annual government procurement volume exceeds **IDR 800 trillion (~$50B USD)**, yet most procurement officers still conduct market surveys manually. This tool aims to close that gap.

## License

MIT
