"""SQLite persistence (stdlib only). One connection per call keeps it thread-safe for the prototype."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
  role TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, department TEXT, source_url TEXT,
  version TEXT, review_date TEXT, status TEXT DEFAULT 'Active', filename TEXT, is_synthetic INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_number INTEGER, section TEXT, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS services(
  id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE, name TEXT, description TEXT, category TEXT,
  department TEXT, info_url TEXT, contact TEXT, keywords TEXT, last_reviewed TEXT);
CREATE TABLE IF NOT EXISTS enquiries(
  id INTEGER PRIMARY KEY AUTOINCREMENT, reference_number TEXT UNIQUE NOT NULL, category TEXT,
  description TEXT NOT NULL, suggested_department TEXT, confirmed_department TEXT,
  routing_confidence REAL, status TEXT NOT NULL DEFAULT 'Submitted', contact_name TEXT, contact_detail TEXT,
  staff_notes TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT NOT NULL, record_type TEXT, record_id TEXT,
  detail TEXT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chat_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, answered INTEGER, timestamp TEXT DEFAULT CURRENT_TIMESTAMP);
"""


def _connect():
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def conn():
    con = _connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)
        cols = {r[1] for r in c.execute("PRAGMA table_info(documents)")}
        for name, default in [('classification','Public'),('repository','Public library'),('owner','Demo policy team'),('policy_key','')]:
            if name not in cols:
                c.execute(f"ALTER TABLE documents ADD COLUMN {name} TEXT DEFAULT '{default}'")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS source_pages(document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE, page INTEGER, text TEXT, PRIMARY KEY(document_id,page));
        CREATE TABLE IF NOT EXISTS programmes(id INTEGER PRIMARY KEY, name TEXT, description TEXT, policy_key TEXT);
        CREATE TABLE IF NOT EXISTS rules(id INTEGER PRIMARY KEY, programme_id INTEGER, version INTEGER, policy_document INTEGER, criteria TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, actor TEXT);
        CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY, reference TEXT UNIQUE, programme_id INTEGER, applicant TEXT, declared TEXT, status TEXT DEFAULT 'Submitted', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY, application_id INTEGER, kind TEXT, filename TEXT, text TEXT, fields TEXT, confidence REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS assessments(id INTEGER PRIMARY KEY, application_id INTEGER, rule_id INTEGER, recommendation TEXT, confidence REAL, results TEXT, snapshot TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, application_id INTEGER, assessment_id INTEGER, decision TEXT, reason TEXT, actor TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)


def rows(sql, params=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def one(sql, params=()):
    r = rows(sql, params)
    return r[0] if r else None


def execute(sql, params=()):
    with conn() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def audit(actor, action, record_type=None, record_id=None, detail=None):
    execute("INSERT INTO audit_events(actor,action,record_type,record_id,detail) VALUES(?,?,?,?,?)",
            (actor, action, record_type, str(record_id) if record_id is not None else None, detail))
