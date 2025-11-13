from datetime import datetime, timezone
from typing import List, Dict, Optional
import re

from dateutil import parser as dtparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from db import connect, init_db

BASE_URL = "https://www.enforcementtracker.com"

# -------------------- parsing helpers --------------------

def parse_amount_eur(raw: str) -> Optional[float]:
    if not raw:
        return None
    txt = str(raw).strip()
    txt = txt.replace("€", "").replace("\u00A0", "").replace(" ", "")
    txt = txt.replace(",", ".")  # decimal comma -> dot
    # remove thousand separators between digit groups
    txt = re.sub(r"(?<=\d)[.,](?=\d{3}(\D|$))", "", txt)
    try:
        return float(txt)
    except ValueError:
        return None

def parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    try:
        return dtparse.parse(str(raw).strip(), dayfirst=True).date().isoformat()
    except Exception:
        return None

def absolute_url(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith("http"):
        return href
    return f"{BASE_URL.rstrip('/')}/{href.lstrip('/')}"

# -------------------- DB --------------------

def upsert_rows(rows: List[Dict]) -> None:
    scraped_at = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        for r in rows:
            con.execute(
                """
                INSERT INTO fines (
                  etid, country, authority, decision_date, amount_eur,
                  controller_or_processor, quoted_articles, type, summary,
                  source_url, direct_url, scraped_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(etid) DO UPDATE SET
                  country=excluded.country,
                  authority=COALESCE(excluded.authority, fines.authority),
                  decision_date=excluded.decision_date,
                  amount_eur=excluded.amount_eur,
                  controller_or_processor=excluded.controller_or_processor,
                  quoted_articles=excluded.quoted_articles,
                  type=excluded.type,
                  summary=COALESCE(excluded.summary, fines.summary),
                  source_url=COALESCE(excluded.source_url, fines.source_url),
                  direct_url=COALESCE(excluded.direct_url, fines.direct_url),
                  scraped_at=excluded.scraped_at
                """,
                (
                    r["etid"], r["country"], r["authority"], r["decision_date"],
                    r["amount_eur"], r["controller_or_processor"], r["quoted_articles"],
                    r["type"], r["summary"], r["source_url"], r["direct_url"], scraped_at,
                ),
            )
        con.commit()

# -------------------- page helpers --------------------

def click_if_exists(page, selectors, timeout_ms=2000) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=timeout_ms)
                page.wait_for_timeout(150)
                return True
        except Exception:
            pass
    return False

def wait_for_table_selector(page) -> str:
    for sel in ["table.dataTable tbody tr", "table#datatable tbody tr", "table tbody tr"]:
        try:
            page.wait_for_selector(sel, timeout=60_000)
            return sel
        except PlaywrightTimeoutError:
            continue
    raise RuntimeError("No table rows detected.")

def set_page_length(page, row_sel: str, length: int = 100) -> None:
    for css in ["div.dataTables_length select", 'select[name$="_length"]', "select#datatable_length select"]:
        if page.locator(css).count() > 0:
            try:
                page.select_option(css, value=str(length))
            except Exception:
                page.select_option(css, label=str(length))
            page.wait_for_timeout(600)
            break

def force_visible_columns(page) -> None:
    page.add_style_tag(content="""
    .dtr-hidden { display: table-cell !important; }
    table.dataTable thead th, table.dataTable tbody td { white-space: nowrap; }
    """)
    page.wait_for_timeout(150)

# -------------------- child-row extraction (authority/sector/summary/urls) --------------------

def norm_label(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("€", "e")
    s = s.replace("controller / processor", "controller/processor")
    s = re.sub(r"\s+", " ", s)
    return s

def extract_child_kv(child_tr) -> Dict[str, str]:
    """Parse DataTables Responsive child: <span class='dtr-title'>Label</span><span class='dtr-data'>Value</span>"""
    kv = {}
    if not child_tr:
        return kv
    titles = child_tr.locator("span.dtr-title")
    datas  = child_tr.locator("span.dtr-data")
    n = min(titles.count(), datas.count())
    for i in range(n):
        key = norm_label(titles.nth(i).inner_text() or "")
        val = (datas.nth(i).inner_text() or "").strip()
        if key:
            kv[key] = val
    return kv

def extract_child_freeform(child_tr) -> Dict[str, Optional[str]]:
    """From the expanded child row: Authority / Sector / Summary + links."""
    out = {"authority": "", "sector": "", "summary": "", "direct_url": None, "source_url": None}
    if not child_tr:
        return out

    text = child_tr.inner_text() or ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Authority"):
            out["authority"] = s.split("Authority", 1)[-1].strip(" :")
        elif s.startswith("Sector"):
            out["sector"] = s.split("Sector", 1)[-1].strip(" :")
        elif s.startswith("Summary"):
            out["summary"] = s.split("Summary", 1)[-1].strip(" :")

    anchors = child_tr.locator("a[href]")
    for i in range(min(anchors.count(), 10)):
        href = anchors.nth(i).get_attribute("href")
        if not href:
            continue
        full = absolute_url(href)
        if not full:
            continue
        if "/etid-" in full.lower():
            out["direct_url"] = full
        if not out["source_url"]:
            out["source_url"] = full

    return out

# -------------------- header map for main row --------------------

def build_header_map(page) -> Dict[str, Optional[int]]:
    """
    Return indices (0-based among TDs) for each logical column based on <thead> text.
    We look for substrings rather than exact matches to be robust to punctuation.
    """
    keys = {
        "etid": ["etid"],
        "country": ["country"],
        "date": ["date of decision", "decision date", "date"],
        "fine": ["fine"],
        "controller": ["controller", "processor", "controller/processor"],
        "quoted": ["quoted art", "article"],
        "type": ["type"],
        "source": ["source"],
    }

    ths = page.query_selector_all("table thead th")
    labels = []
    for th in ths:
        txt = (th.inner_text() or "").strip().lower()
        txt = txt.replace("€", "e")
        txt = re.sub(r"\s+", " ", txt)
        labels.append(txt)

    # Build map: which TD index corresponds to which logical key
    # There is usually a leading "View" column (expand toggle). We keep it in labels, but we don't map to it.
    header_map: Dict[str, Optional[int]] = {k: None for k in keys.keys()}

    for idx, lab in enumerate(labels):
        for key, patterns in keys.items():
            if any(pat in lab for pat in patterns):
                header_map[key] = idx  # TD index matches TH index order
                break

    print("Header detected:", header_map, flush=True)
    return header_map

# -------------------- main --------------------

def run(max_pages: Optional[int] = None) -> None:
    init_db()
    total = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
        )
        page = context.new_page()

        # Load list page & settle
        page.goto(BASE_URL, timeout=120_000, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=60_000)
        click_if_exists(page, [
            "button:has-text('Accept')", "button:has-text('Accept all')",
            "[aria-label='Accept']", "text=Allow all", "text=OK",
        ])

        sel = wait_for_table_selector(page)
        set_page_length(page, sel, 100)
        force_visible_columns(page)

        # Build the header map once per page (rebuild after each pagination)
        header_map = build_header_map(page)

        page_index = 0
        seen: set[str] = set()

        while True:
            page_index += 1
            batch: List[Dict] = []

            idx = 0
            while True:
                rows = page.locator(sel)
                count = rows.count()
                if idx >= count or count == 0:
                    break

                tr = rows.nth(idx)
                if "child" in ((tr.get_attribute("class") or "").lower()):
                    idx += 1
                    continue

                cells = tr.locator("td")
                td_count = cells.count()
                if td_count == 0:
                    idx += 1
                    continue

                # Expand to get the child row (Authority/Sector/Summary/Direct URL)
                try:
                    cells.first.click()
                    page.wait_for_timeout(100)
                except Exception:
                    pass

                rows = page.locator(sel)
                count = rows.count()
                child = None
                step = 1
                if idx + 1 < count:
                    maybe = rows.nth(idx + 1)
                    if "child" in ((maybe.get_attribute("class") or "").lower()):
                        child = maybe
                        step = 2

                kv  = extract_child_kv(child)
                det = extract_child_freeform(child)

                # Helper to read main cells by header index
                def safe_text(header_key: str) -> str:
                    i = header_map.get(header_key)
                    if i is None or i >= td_count:
                        return ""
                    return (cells.nth(i).inner_text() or "").strip()

                def safe_href(header_key: str) -> Optional[str]:
                    i = header_map.get(header_key)
                    if i is None or i >= td_count:
                        return None
                    a = cells.nth(i).locator("a[href]")
                    return a.first.get_attribute("href") if a.count() > 0 else None

                # Read from main row via header map (robust to responsive shifts)
                etid_txt   = safe_text("etid") or kv.get("etid") or ""
                country    = safe_text("country") or kv.get("country") or ""
                date_txt   = safe_text("date") or kv.get("date of decision") or kv.get("date") or ""
                fine_txt   = safe_text("fine") or kv.get("fine e") or kv.get("fine €") or kv.get("fine") or ""
                controller = safe_text("controller") or kv.get("controller/processor") or ""
                quoted     = safe_text("quoted") or kv.get("quoted art.") or kv.get("quoted art") or ""
                typ        = safe_text("type") or kv.get("type") or ""
                source_url = absolute_url(safe_href("source") or kv.get("source"))

                # Direct URL / Authority / Sector / Summary from child
                direct_url = det["direct_url"] or absolute_url(kv.get("direct url"))
                authority  = det["authority"] or ""

                decision_date = parse_date(date_txt)
                amount_eur    = parse_amount_eur(fine_txt)

                # Heartbeat (first 10 rows per page)
                if len(batch) < 10:
                    print(f"[p{page_index:02d} r{len(batch)+1:02d}] "
                          f"etid={etid_txt}, fine_txt={fine_txt!r}, date_txt={date_txt!r}", flush=True)

                if etid_txt and etid_txt not in seen:
                    seen.add(etid_txt)
                    batch.append({
                        "etid": etid_txt,
                        "country": country,
                        "authority": authority,
                        "decision_date": decision_date,
                        "amount_eur": amount_eur,
                        "controller_or_processor": controller,
                        "quoted_articles": quoted,
                        "type": typ,
                        "summary": (f"Sector: {det['sector']}. " if det["sector"] else "") + (det["summary"] or ""),
                        "source_url": source_url,
                        "direct_url": direct_url,
                    })

                idx += step

            print(f"Page {page_index}: {len(batch)} fines (expanded)", flush=True)
            if batch:
                upsert_rows(batch)
                total += len(batch)

            # Next page
            moved = False
            for s in ["a.paginate_button.next:not(.disabled)", "li.next:not(.disabled) a"]:
                btn = page.locator(s)
                if btn.count() > 0 and btn.first.is_visible():
                    first_before = page.locator(sel).first.inner_text() if page.locator(sel).count() > 0 else ""
                    btn.first.click()
                    # Rebuild header map after page change
                    for _ in range(20):
                        page.wait_for_timeout(250)
                        first_after = page.locator(sel)
                        if first_after.count() == 0:
                            continue
                        if first_after.first.inner_text() != first_before:
                            header_map = build_header_map(page)
                            moved = True
                            break
                    if moved:
                        break
            if not moved or (max_pages and page_index >= max_pages):
                break

        browser.close()
    print(f"Done. Upserted ~{total} fines (with details).", flush=True)

if __name__ == "__main__":
    # Test a couple pages first; then change to run()
    run()
