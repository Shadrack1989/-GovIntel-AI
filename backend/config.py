"""Central configuration. Everything can be overridden with environment variables."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("GOVASSIST_DATA_DIR", BASE_DIR / "data"))
DOCS_DIR = DATA_DIR / "docs"
DB_PATH = os.getenv("GOVASSIST_DB", str(DATA_DIR / "govassist.db"))

# --- AI (all optional: the app degrades gracefully to extractive answers) ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")
USE_OLLAMA = os.getenv("USE_OLLAMA", "auto").lower()      # auto | on | off
USE_CHROMA = os.getenv("USE_CHROMA", "off").lower()       # off | on  (dense retrieval)
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "60"))

# --- Retrieval ---
TOP_K = int(os.getenv("TOP_K", "4"))
MIN_EVIDENCE = float(os.getenv("MIN_EVIDENCE", "0.22"))   # below => "not enough information"
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "110"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "25"))

# --- Security ---
SECRET_KEY = os.getenv("GOVASSIST_SECRET", "") or secrets.token_hex(32)  # random per start if unset
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", str(8 * 3600)))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
ALLOWED_UPLOAD_EXT = {".pdf", ".txt", ".md", ".docx", ".html", ".htm", ".png", ".jpg", ".jpeg"}
MAX_QUESTION_CHARS = 1000

API_URL = os.getenv("GOVASSIST_API_URL", "http://127.0.0.1:8000")

DEMO_USERS = [
    # username, display name, role, password  (TEST ACCOUNTS ONLY - change before any pilot)
    ("staff", "Thandi Mokoena (Staff)", "staff", os.getenv("DEMO_STAFF_PASSWORD", "staff123")),
    ("admin", "Sipho Dlamini (Admin)", "admin", os.getenv("DEMO_ADMIN_PASSWORD", "admin123")),
]

STATUSES = ["Submitted", "Under Review", "Referred", "Resolved", "Closed"]
