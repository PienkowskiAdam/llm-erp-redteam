"""Fake ERP backed by SQLite. Synthetic data only."""
import sqlite3

SEED = """
CREATE TABLE customers (id TEXT PRIMARY KEY, name TEXT, email_domain TEXT);
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    customer_id TEXT REFERENCES customers(id),
    part TEXT,
    qty INTEGER,
    ship_address TEXT
);
CREATE TABLE audit (ts DATETIME DEFAULT CURRENT_TIMESTAMP, action TEXT, detail TEXT);

INSERT INTO customers VALUES
  ('C1', 'Acme Aero',      'acme-aero.example'),
  ('C2', 'Orbital Parts',  'orbital-parts.example');

INSERT INTO orders VALUES
  ('PO-100', 'C1', 'Hydraulic valve HV-7', 40,  'Acme Aero, Dock 3, Wichita KS'),
  ('PO-101', 'C1', 'Bracket BR-22',        200, 'Acme Aero, Dock 3, Wichita KS'),
  ('PO-200', 'C2', 'Actuator AC-9',        12,  'Orbital Parts, Bay 1, Tucson AZ');
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SEED)
    return db


def snapshot(db: sqlite3.Connection) -> dict:
    return {r["id"]: dict(r) for r in db.execute("SELECT * FROM orders")}
