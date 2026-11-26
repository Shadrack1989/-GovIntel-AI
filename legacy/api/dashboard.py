from datetime import date, timedelta

from fastapi import APIRouter, Depends

from backend import config
from backend.database.db import get_db
from backend.security.auth import require_admin, require_staff

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/stats")
def stats(user: dict = Depends(require_staff)):
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM enquiries").fetchone()[0]
        by_status = {r["status"]: r["n"] for r in db.execute(
            "SELECT status, COUNT(*) n FROM enquiries GROUP BY status")}
        by_category = [dict(r) for r in db.execute(
            "SELECT category, COUNT(*) n FROM enquiries GROUP BY category ORDER BY n DESC")]
        per_day = {r["d"]: r["n"] for r in db.execute(
            "SELECT substr(created_at,1,10) d, COUNT(*) n FROM enquiries GROUP BY d")}
        chat = {r["outcome"]: r["n"] for r in db.execute("SELECT outcome, COUNT(*) n FROM chat_events GROUP BY outcome")}
        topics = [dict(r) for r in db.execute(
            "SELECT topic, COUNT(*) n FROM chat_events WHERE topic IS NOT NULL GROUP BY topic ORDER BY n DESC LIMIT 6")]
        docs = {r["status"]: r["n"] for r in db.execute("SELECT status, COUNT(*) n FROM documents GROUP BY status")}
        stale = db.execute("SELECT COUNT(*) FROM documents WHERE status='Active' AND synthetic=1").fetchone()[0]
        audit_rows = [dict(r) for r in db.execute(
            "SELECT actor,action,record_type,record_id,detail,timestamp FROM audit_events ORDER BY id DESC LIMIT 8")]
    today = date.today()
    trend = [{"date": (today - timedelta(days=i)).isoformat(),
              "count": per_day.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(13, -1, -1)]
    return {
        "total_enquiries": total,
        "open_enquiries": sum(by_status.get(s, 0) for s in config.OPEN_STATUSES),
        "by_status": {s: by_status.get(s, 0) for s in config.ENQUIRY_STATUSES},
        "by_category": by_category, "trend": trend,
        "chat": {"answered": chat.get("answered", 0), "no_answer": chat.get("no_answer", 0),
                 "clarify": chat.get("clarify", 0), "top_topics": topics},
        "documents": {"active": docs.get("Active", 0), "superseded": docs.get("Superseded", 0),
                      "removed": docs.get("Removed", 0), "synthetic_active": stale},
        "recent_audit": audit_rows,
    }


@router.get("/audit")
def audit_log(limit: int = 100, user: dict = Depends(require_admin)):
    with get_db() as db:
        rows = db.execute("SELECT actor,action,record_type,record_id,detail,timestamp FROM audit_events "
                          "ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    return [dict(r) for r in rows]
