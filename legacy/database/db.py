"""SQLite persistence (prototype). Swap for PostgreSQL in a pilot."""
import contextlib
import sqlite3
from datetime import datetime, timezone

from backend import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('staff','admin')),
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  department TEXT NOT NULL,
  service_id TEXT,
  source_url TEXT,
  version TEXT,
  review_date TEXT,
  status TEXT NOT NULL DEFAULT 'Active',
  filename TEXT,
  synthetic INTEGER NOT NULL DEFAULT 1,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_number INTEGER,
  section TEXT,
  kind TEXT NOT NULL DEFAULT 'info',
  text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enquiries(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reference_number TEXT UNIQUE NOT NULL,
  category TEXT NOT NULL,
  description TEXT NOT NULL,
  contact_name TEXT,
  contact_email TEXT,
  suggested_department TEXT,
  routing_confidence TEXT,
  final_department TEXT,
  status TEXT NOT NULL DEFAULT 'Submitted',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enquiry_notes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  enquiry_id INTEGER NOT NULL REFERENCES enquiries(id) ON DELETE CASCADE,
  author TEXT NOT NULL,
  note TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  record_type TEXT,
  record_id TEXT,
  detail TEXT,
  timestamp TEXT NOT NULL
);
-- Chat analytics deliberately store NO question text (data minimisation): topic + outcome only.
CREATE TABLE IF NOT EXISTS chat_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic TEXT,
  outcome TEXT NOT NULL,
  timestamp TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextlib.contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as db:
        db.executescript(SCHEMA)


def audit(db, actor: str, action: str, record_type: str = "", record_id="", detail: str = "") -> None:
    db.execute(
        "INSERT INTO audit_events(actor,action,record_type,record_id,detail,timestamp) VALUES(?,?,?,?,?,?)",
        (actor, action, record_type, str(record_id), detail[:500], now_iso()),
    )
