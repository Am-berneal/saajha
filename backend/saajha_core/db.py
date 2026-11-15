"""SQLite storage: ledger events, agent cases, AI call log."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path

DATA_DIR = Path(os.environ.get("SAAJHA_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("SAAJHA_DB", DATA_DIR / "saajha.db"))

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id TEXT NOT NULL,
  type TEXT NOT NULL,
  payload TEXT NOT NULL,
  ts TEXT NOT NULL,
  signer TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL,
  signature TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  feature TEXT, engine TEXT, model TEXT, language TEXT,
  latency_ms INTEGER, valid INTEGER, retried INTEGER, fallback TEXT,
  confidence REAL, summary TEXT, error TEXT
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(path or DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


_con: sqlite3.Connection | None = None


def con() -> sqlite3.Connection:
    global _con
    if _con is None:
        _con = connect()
    return _con


def reset_for_tests(path: str) -> None:
    global _con
    _con = connect(path)


def q(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        cur = con().execute(sql, args)
        rows = cur.fetchall()
        con().commit()
        return rows


def exec_(sql: str, args: tuple = ()) -> int:
    with _lock:
        cur = con().execute(sql, args)
        con().commit()
        return cur.lastrowid


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
