from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from db import connect, init_db
import json

app = FastAPI(title="GDPR Fines API", version="1.0.0")

def row_to_dict(row):
    return {
        "etid": row["etid"],
        "country": row["country"],
        "authority": row["authority"],
        "decision_date": row["decision_date"],
        "amount_eur": row["amount_eur"],
        "controller_or_processor": row["controller_or_processor"],
        "quoted_articles": row["quoted_articles"],
        "type": row["type"],
        "summary": row["summary"],
        "source_url": row["source_url"],
        "direct_url": row["direct_url"],
        "scraped_at": row["scraped_at"],
    }

@app.on_event("startup")
def _startup():
    init_db()

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/fines")
def list_fines(
    country: Optional[str] = None,
    authority: Optional[str] = None,
    article: Optional[str] = Query(None, description="Substring match in quoted_articles"),
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    controller: Optional[str] = Query(None, description="Substring match in controller_or_processor"),
    type_: Optional[str] = Query(None, alias="type", description="Type column"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = 100,
    offset: int = 0,
):
    sql = "SELECT * FROM fines WHERE 1=1"
    params: List[object] = []

    if country:
        sql += " AND country = ?"
        params.append(country)
    if authority:
        sql += " AND authority = ?"
        params.append(authority)
    if article:
        sql += " AND quoted_articles LIKE ?"
        params.append(f"%{article}%")
    if controller:
        sql += " AND controller_or_processor LIKE ?"
        params.append(f"%{controller}%")
    if type_:
        sql += " AND type = ?"
        params.append(type_)
    if min_amount is not None:
        sql += " AND amount_eur >= ?"
        params.append(min_amount)
    if max_amount is not None:
        sql += " AND amount_eur <= ?"
        params.append(max_amount)
    if date_from:
        sql += " AND decision_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND decision_date <= ?"
        params.append(date_to)

    sql += " ORDER BY decision_date DESC, amount_eur DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with connect() as con:
        rows = con.execute(sql, params).fetchall()
        return [row_to_dict(r) for r in rows]

@app.get("/fines/{etid}")
def get_fine(etid: str):
    with connect() as con:
        row = con.execute("SELECT * FROM fines WHERE etid = ?", (etid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="ETID not found")
        return row_to_dict(row)

@app.get("/stats")
def stats():
    sql = """
    SELECT substr(COALESCE(decision_date,''),1,7) AS ym,
           COUNT(*) AS count,
           SUM(COALESCE(amount_eur,0)) AS total_eur
    FROM fines
    GROUP BY ym
    ORDER BY ym DESC
    """
    with connect() as con:
        rows = con.execute(sql).fetchall()
        return [{"year_month": r["ym"], "count": r["count"], "total_eur": r["total_eur"]} for r in rows]

@app.get("/fines.jsonl")
def export_jsonl():
    with connect() as con:
        rows = con.execute("SELECT * FROM fines ORDER BY decision_date DESC").fetchall()
        lines = [json.dumps(row_to_dict(r), ensure_ascii=False) for r in rows]
        content = "\n".join(lines)
        return PlainTextResponse(content, media_type="application/x-jsonlines")
