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

### Base URL

* **Local**: `http://localhost:8000`
* **Codespaces (Public Port 8000)**: the forwarded URL shown in the **PORTS** panel

### `GET /fines`

Returns fines with optional filters.

**Query Parameters**

| Param                       | Description                        |
| --------------------------- | ---------------------------------- |
| `country`                   | Filter by country                  |
| `controller`                | Substring match on controller name |
| `article`                   | Filter by cited GDPR article       |
| `type`                      | Filter by category                 |
| `min_amount` / `max_amount` | Filter numeric range (EUR)         |
| `from` / `to`               | Decision date range (YYYY-MM-DD)   |
| `limit` / `offset`          | Pagination                         |

**Examples**

```bash
# Top fines in Spain since 2023 (curl)
curl "http://localhost:8000/fines?country=SPAIN&from=2023-01-01&min_amount=1000000&limit=50"

# Articles matching Art. 5(1)(f) (curl)
curl "http://localhost:8000/fines?article=5(1)(f)"
```

**Python**

```python
import requests
r = requests.get("http://localhost:8000/fines", params={
    "country": "FRANCE",
    "min_amount": 1_000_000,
    "from": "2023-01-01"
})
print(r.json()[:3])
```

**JavaScript (browser / Node)**

```js
const base = "http://localhost:8000"; // or your public URL
const res = await fetch(`${base}/fines?country=ITALY&limit=5`);
const data = await res.json();
console.log(data);
```

### `GET /fines/{etid}`

Retrieve one fine by ETID.

### `GET /stats`

Basic aggregate counts and totals.

### `GET /fines.jsonl`

Line-delimited JSON export for GPT ingestion.

---

## Updating the Custom GPT Dataset

## Operational Runbook

### Manual refresh (local or Codespaces)

1. Activate venv: `source .venv/bin/activate`
2. Full scrape: `python -u scraper_playwright.py` (ensure the last line is `run()`)
3. Start API: `uvicorn api:app --host 0.0.0.0 --port 8000`
4. Download `/fines.jsonl` and upload to your Custom GPT.

### Suggested cadence

* Weekly or monthly, depending on how often the tracker updates.

### Host / deploy options

* **Codespaces (simple):** keep port 8000 Public while testing.
* **Local machine:** run the same commands; share via a tunnel (e.g., Cloudflare Tunnel or `ssh -R`).
* **Docker:** build and run the API anywhere that supports containers.

**Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium
COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build & run:

```bash
docker build -t gdpr-et-api .
docker run --rm -p 8000:8000 gdpr-et-api
```

> To refresh data inside the container, either mount a volume with `fines.db` or run the scraper in the container: `docker run --rm gdpr-et-api python -u scraper_playwright.py`.

### Automation (GitHub Actions)

Create `.github/workflows/scrape.yml` to refresh on a schedule and attach the dataset as an artifact or commit it to `data/`.

```yaml
name: Refresh fines dataset
on:
  schedule: [{ cron: '0 5 * * 1' }]  # every Monday 05:00 UTC
  workflow_dispatch: {}

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          python -m playwright install --with-deps chromium
      - name: Run scraper (full)
        env:
          PYTHONUNBUFFERED: '1'
        run: |
          python - << 'PY'
          from scraper_playwright import run
          run()  # full scrape
          PY
      - name: Export JSONL
        run: |
          python - << 'PY'
          import json, sqlite3
          con = sqlite3.connect('fines.db')
          cur = con.execute('SELECT etid,country,authority,decision_date,amount_eur,controller_or_processor,quoted_articles,type,summary,source_url,direct_url,scraped_at FROM fines')
          with open('fines.jsonl','w',encoding='utf-8') as f:
            for row in cur:
              obj = {
                'etid': row[0], 'country': row[1], 'authority': row[2], 'decision_date': row[3],
                'amount_eur': row[4], 'controller_or_processor': row[5], 'quoted_articles': row[6],
                'type': row[7], 'summary': row[8], 'source_url': row[9], 'direct_url': row[10], 'scraped_at': row[11]
              }
              f.write(json.dumps(obj, ensure_ascii=False) + '
')
          PY
      - name: Upload artifact (fines.jsonl)
        uses: actions/upload-artifact@v4
        with:
          name: fines-jsonl
          path: fines.jsonl
      # Optional: commit dataset into repo (data/)
      - name: Commit updated dataset
        if: ${{ github.ref == 'refs/heads/main' }}
        run: |
          mkdir -p data
          mv fines.jsonl data/fines.jsonl
          git config user.name "github-actions"
          git config user.email "github-actions@users.noreply.github.com"
          git add data/fines.jsonl fines.db || true
          git commit -m "chore: refresh dataset" || echo "No changes to commit"
          git push || true
```

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
