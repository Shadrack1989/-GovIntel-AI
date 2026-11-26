"""Password hashing, sessions and role-based access control."""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException

from backend import config
from backend.database.db import get_db, now_iso

PBKDF2_ITERATIONS = 200_000
_failures: dict[str, list[float]] = {}


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _locked(username: str) -> bool:
    cutoff = time.time() - config.LOCKOUT_SECONDS
    recent = [t for t in _failures.get(username, []) if t > cutoff]
    _failures[username] = recent
    return len(recent) >= config.MAX_LOGIN_FAILURES


def authenticate(username: str, password: str):
    """Return the user row, or raise 401/429. Never reveals which field was wrong."""
    key = username.lower()
    if _locked(key):
        raise HTTPException(429, "Too many failed sign-in attempts. Please wait a few minutes and try again.")
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE username=?", (key,)).fetchone()
    # Always run a hash to keep timing similar for unknown users.
    ok = verify_password(password, user["password_hash"] if user else hash_password("x"))
    if not (user and ok):
        _failures.setdefault(key, []).append(time.time())
        raise HTTPException(401, "Incorrect username or password.")
    _failures.pop(key, None)
    return user


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=config.SESSION_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))
        db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(), user_id, expires))
    return token


def destroy_session(token: str) -> None:
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))


def _token_from_header(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(authorization: str | None = Header(default=None)) -> dict:
    token = _token_from_header(authorization)
    if not token:
        raise HTTPException(401, "Please sign in.")
    with get_db() as db:
        row = db.execute(
            "SELECT u.id,u.username,u.display_name,u.role FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.expires_at > ?",
            (hashlib.sha256(token.encode()).hexdigest(), now_iso()),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    return dict(row)


def require_role(*roles: str):
    def checker(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "You do not have permission to do that.")
        return user
    return checker


require_staff = require_role("staff", "admin")
require_admin = require_role("admin")
