import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend import config
from backend.database.db import audit, get_db, now_iso
from backend.security.auth import require_staff
from backend.services import routing_service

router = APIRouter(prefix="/api/enquiries", tags=["enquiries"])

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alikes (0/O, 1/I)


def new_reference() -> str:
    return "GA-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


class EnquiryIn(BaseModel):
    description: str = Field(min_length=10, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    contact_name: str | None = Field(default=None, max_length=100)
    contact_email: str | None = Field(default=None, max_length=120)


class SuggestIn(BaseModel):
    description: str = Field(min_length=3, max_length=2000)


class EnquiryPatch(BaseModel):
    status: str | None = None
    final_department: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=1000)


@router.post("/suggest")
def suggest(body: SuggestIn):
    return routing_service.classify(body.description)


@router.post("", status_code=201)
def create_enquiry(body: EnquiryIn):
    route = routing_service.classify(body.description)
    valid = {s["category"] for s in routing_service.public_services()} | {"General enquiry"}
    category = body.category if body.category in valid else route["category"]
    with get_db() as db:
        for _ in range(5):
            ref = new_reference()
            if not db.execute("SELECT 1 FROM enquiries WHERE reference_number=?", (ref,)).fetchone():
                break
        now = now_iso()
        cur = db.execute(
            "INSERT INTO enquiries(reference_number,category,description,contact_name,contact_email,"
            "suggested_department,routing_confidence,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (ref, category, body.description.strip(), (body.contact_name or "").strip() or None,
             (body.contact_email or "").strip() or None, route["department"], route["confidence"],
             "Submitted", now, now),
        )
        audit(db, "citizen", "enquiry.created", "enquiry", cur.lastrowid, ref)
    return {"reference_number": ref, "status": "Submitted", "category": category,
            "suggested_department": route["department"], "routing_note": route["note"]}


@router.get("/track/{reference}")
def track(reference: str):
    """Public status lookup by reference number. Returns status only (no description or contact details)."""
    with get_db() as db:
        row = db.execute("SELECT reference_number,category,status,created_at,updated_at FROM enquiries "
                         "WHERE reference_number=?", (reference.strip().upper(),)).fetchone()
    if not row:
        raise HTTPException(404, "We couldn't find an enquiry with that reference number.")
    return dict(row)


@router.get("")
def list_enquiries(
    q: str = Query(default="", max_length=100),
    status: str = Query(default="", max_length=30),
    category: str = Query(default="", max_length=80),
    user: dict = Depends(require_staff),
):
    sql, args = "SELECT * FROM enquiries WHERE 1=1", []
    if q:
        sql += " AND (reference_number LIKE ? OR description LIKE ? OR category LIKE ?)"
        args += [f"%{q}%"] * 3
    if status:
        sql += " AND status=?"
        args.append(status)
    if category:
        sql += " AND category=?"
        args.append(category)
    sql += " ORDER BY id DESC LIMIT 500"
    with get_db() as db:
        rows = [dict(r) for r in db.execute(sql, args).fetchall()]
    return rows


@router.get("/{enquiry_id}")
def get_enquiry(enquiry_id: int, user: dict = Depends(require_staff)):
    with get_db() as db:
        row = db.execute("SELECT * FROM enquiries WHERE id=?", (enquiry_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Enquiry not found.")
        notes = db.execute("SELECT author,note,created_at FROM enquiry_notes WHERE enquiry_id=? ORDER BY id",
                           (enquiry_id,)).fetchall()
    return {**dict(row), "notes": [dict(n) for n in notes]}


@router.patch("/{enquiry_id}")
def update_enquiry(enquiry_id: int, body: EnquiryPatch, user: dict = Depends(require_staff)):
    if body.status and body.status not in config.ENQUIRY_STATUSES:
        raise HTTPException(400, f"Status must be one of: {', '.join(config.ENQUIRY_STATUSES)}.")
    with get_db() as db:
        row = db.execute("SELECT * FROM enquiries WHERE id=?", (enquiry_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Enquiry not found.")
        changes = []
        if body.status and body.status != row["status"]:
            db.execute("UPDATE enquiries SET status=? WHERE id=?", (body.status, enquiry_id))
            changes.append(f"status {row['status']} → {body.status}")
        if body.final_department and body.final_department != (row["final_department"] or row["suggested_department"]):
            db.execute("UPDATE enquiries SET final_department=? WHERE id=?", (body.final_department, enquiry_id))
            changes.append(f"referral → {body.final_department}")
        if body.note and body.note.strip():
            db.execute("INSERT INTO enquiry_notes(enquiry_id,author,note,created_at) VALUES(?,?,?,?)",
                       (enquiry_id, user["display_name"], body.note.strip(), now_iso()))
            changes.append("note added")
        if changes:
            db.execute("UPDATE enquiries SET updated_at=? WHERE id=?", (now_iso(), enquiry_id))
            audit(db, user["username"], "enquiry.updated", "enquiry", enquiry_id,
                  f"{row['reference_number']}: " + "; ".join(changes))
    return get_enquiry(enquiry_id, user)
