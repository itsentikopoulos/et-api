import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("fines.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS fines (
  etid TEXT PRIMARY KEY,
  country TEXT,
  authority TEXT,
  decision_date TEXT,
  amount_eur REAL,
  controller_or_processor TEXT,
  quoted_articles TEXT,
  type TEXT,
  summary TEXT,
  source_url TEXT,
  direct_url TEXT,
  scraped_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_country ON fines(country);
CREATE INDEX IF NOT EXISTS idx_decision_date ON fines(decision_date);
CREATE INDEX IF NOT EXISTS idx_amount ON fines(amount_eur);
"""

@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()

def init_db():
    with connect() as con:
        con.executescript(SCHEMA)
        con.commit()
