# GDPR Enforcement Tracker — Scraper + API

## Overview

This repository automates extraction of GDPR enforcement data from **[enforcementtracker.com](https://www.enforcementtracker.com)**. It provides a **FastAPI server** for local querying and a downloadable **`fines.jsonl` dataset** designed for use in Custom GPTs. The goal is to maintain an up‑to‑date, structured database of GDPR fines for analysis or AI‑based Q&A.

> ⚠️ **Disclaimer:** The Enforcement Tracker is maintained by CMS Law. Use this scraper only for personal or research purposes. Do not republish or redistribute scraped data without permission.

---

## Architecture

```text
┌──────────────────┐       Playwright scrape       ┌────────────────────────┐
│ EnforcementTracker│ ───────────────────────────▶ │ SQLite (fines.db)      │
└──────────────────┘                              └────────┬───────────────┘
                                                         │
                                                         ▼
                                               ┌────────────────┐
                                               │ FastAPI server │
                                               └──────┬─────────┘
                                            /fines, /stats, /fines.jsonl
```

* **`scraper_playwright.py`** — uses Playwright to scrape fines, expand details, parse fields, and save to SQLite.
* **`db.py`** — creates and manages the local database.
* **`api.py`** — exposes REST endpoints and JSONL export.

---

## Data Model

**Table: `fines`**

| Column                    | Type       | Description                               |
| ------------------------- | ---------- | ----------------------------------------- |
| `etid`                    | TEXT (PK)  | Enforcement Tracker ID (e.g. `ETid-2915`) |
| `country`                 | TEXT       | Country of the authority issuing the fine |
| `authority`               | TEXT       | Extracted from expanded child row         |
| `decision_date`           | TEXT (ISO) | Decision date (YYYY-MM-DD)                |
| `amount_eur`              | REAL       | Fine amount in EUR                        |
| `controller_or_processor` | TEXT       | Controller / Processor name               |
| `quoted_articles`         | TEXT       | Cited GDPR articles                       |
| `type`                    | TEXT       | Type/category of infringement             |
| `summary`                 | TEXT       | Descriptive summary                       |
| `source_url`              | TEXT       | External source link                      |
| `direct_url`              | TEXT       | Canonical Enforcement Tracker page        |
| `scraped_at`              | TEXT (ISO) | Timestamp of data ingestion               |

---

## Quick Start (GitHub Codespaces)

### 1️⃣ Activate the virtual environment

```bash
source .venv/bin/activate
```

### 2️⃣ Test scrape (2 pages)

```bash
python -u scraper_playwright.py
```

### 3️⃣ Full scrape

Edit the last line of `scraper_playwright.py` from:

```python
run(max_pages=2)
```

to:

```python
run()
```

Then run:

```bash
python -u scraper_playwright.py
```

### 4️⃣ Start the API

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Mark port **8000** as **Public** in Codespaces.

### 5️⃣ Access endpoints

| Path            | Description                  |
| --------------- | ---------------------------- |
| `/health`       | Health check                 |
| `/fines`        | All fines with query filters |
| `/fines/{etid}` | Retrieve a single fine       |
| `/stats`        | Aggregated counts            |
| `/fines.jsonl`  | JSONL export for GPT         |

---

## Local Setup (Alternative)

**Requirements**

* Python 3.11+
* Playwright installed

**Install and configure:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Run scraper:

```bash
python -u scraper_playwright.py
```

---

## API Reference

### `GET /fines`

Returns fines with filters.

**Query Parameters**

| Param                       | Description                        |
| --------------------------- | ---------------------------------- |
| `country`                   | Filter by country                  |
| `controller`                | Substring match on controller name |
| `article`                   | Filter by cited GDPR article       |
| `type`                      | Filter by category                 |
| `min_amount` / `max_amount` | Filter numeric range               |
| `from` / `to`               | Decision date range                |
| `limit` / `offset`          | Pagination                         |

**Example:**

```bash
curl "http://localhost:8000/fines?country=FRANCE&min_amount=1000000"
```

### `GET /fines/{etid}`

Retrieve one fine by ETID.

### `GET /stats`

Basic aggregate counts and totals.

### `GET /fines.jsonl`

Line-delimited JSON export for GPT ingestion.

---

## Updating the Custom GPT Dataset

1. Run a **full scrape** and start the API.
2. Visit `/fines.jsonl` (Codespace port 8000 → Public → Browser).
3. Save the file locally.
4. In **ChatGPT → Custom GPT → Configure → Knowledge**, upload the file.
5. Example queries:

   * “Top 10 fines since 2023 with ETID, controller, amount, date, country.”
   * “List France fines citing Art. 5(1)(f) GDPR.”

---

## Operational Runbook

| Task            | Command                                          |
| --------------- | ------------------------------------------------ |
| Refresh dataset | `python -u scraper_playwright.py`                |
| Export dataset  | Download `/fines.jsonl`                          |
| Start API       | `uvicorn api:app --host 0.0.0.0 --port 8000`     |
| Verify rows     | `sqlite3 fines.db 'select count(*) from fines;'` |

**Recommended cadence:** Refresh monthly or when new fines appear.

---

## Troubleshooting

**1️⃣ `amount=None` / `date=None`**
Use the header-map version of the scraper (this repo’s latest). Check for `Header detected:` logs.

**2️⃣ SSL handshake or proxy errors**
Run inside **Codespaces** (these environments are preconfigured for Playwright).

**3️⃣ API 404 / Not Found**
Ensure server is running: `uvicorn api:app --host 0.0.0.0 --port 8000` and port 8000 is **Public**.

**4️⃣ Cookie consent issues**
Add new button text to `click_if_exists()` if CMS updates consent banners.

---

## Ethics & Attribution

* Source: **CMS’s GDPR Enforcement Tracker**.
* Always verify fine amounts/dates via official decisions.
* Use moderate scrape frequency to avoid site strain.
* This repository is for research/internal use.

---

## File Summary

| File                    | Description                                    |
| ----------------------- | ---------------------------------------------- |
| `scraper_playwright.py` | Main scraper (Playwright + header map parsing) |
| `db.py`                 | Initializes and manages SQLite schema          |
| `api.py`                | FastAPI server exposing endpoints              |
| `fines.db`              | Local SQLite dataset                           |
| `fines.jsonl`           | Export file for Custom GPT                     |

---

## Future Enhancements

* Add `/search` endpoint (FTS5 full‑text)
* Add `/fines.csv` or `/fines.xlsx` export
* Automate weekly scraping via GitHub Actions
* Add upload timestamp summary in `/stats`

---

**Maintainer:** Ioannis Tsentikopoulos
**Environment:** GitHub Codespaces
**Language:** Python 3.11 + Playwright + FastAPI
**License:** Internal / Research use only
