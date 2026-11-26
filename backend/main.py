"""GovIntel AI - FastAPI application."""
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from . import config, db, llm, retrieval, routing, security, seed
from .textutil import tokens

@asynccontextmanager
async def lifespan(_app):
    seed.run()
    from . import govintel
    govintel.seed_demo()
    yield


app = FastAPI(title="GovIntel AI", version="0.1.0", lifespan=lifespan,
              description="Prototype. Public/synthetic data only. Not an official government service.")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# --- tiny in-memory rate limiter for public endpoints --------------------------------
_hits = defaultdict(deque)


def rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 40:
        raise HTTPException(429, "Too many requests - please wait a minute.")
    q.append(now)


# --- models ----------------------------------------------------------------------------
class LoginIn(BaseModel):
    username: str = Field(max_length=60)
    password: str = Field(max_length=200)


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=config.MAX_QUESTION_CHARS)
    language: str = "en"


class EnquiryIn(BaseModel):
    description: str = Field(min_length=10, max_length=2000)
    category: Optional[str] = Field(default=None, max_length=80)
    contact_name: Optional[str] = Field(default=None, max_length=80)
    contact_detail: Optional[str] = Field(default=None, max_length=120)


class EnquiryPatch(BaseModel):
    status: Optional[str] = None
    confirmed_department: Optional[str] = Field(default=None, max_length=120)
    note: Optional[str] = Field(default=None, max_length=1000)


# --- helpers ---------------------------------------------------------------------------
ELIGIBILITY = re.compile(r"\b(am i eligible|do i qualify|will i (get|be approved)|can i get|entitled|qualify for)\b", re.I)
GREETING = re.compile(r"^\s*(hi|hello|hey|molo|sawubona|dumela|good (morning|afternoon|evening))\W*$", re.I)
TRANSLATION_WARNING = ("Responses in languages other than English are machine-generated and may need confirmation "
                       "with the relevant department.")


def _excerpt(text, n=320):
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def _sources(passages):
    out = []
    for i, p in enumerate(passages, 1):
        out.append({"n": i, "title": p["title"], "section": p["section"], "page": p["page_number"],
                    "department": p["department"], "url": p["source_url"], "review_date": p["review_date"],
                    "version": p["version"], "status": p["status"], "id": p["document_id"], "repository": p["repository"], "synthetic": bool(p["is_synthetic"]), "excerpt": _excerpt(p["text"])})
    return out


# --- routes ----------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat(timespec="seconds"),
            "documents": db.one("SELECT COUNT(*) n FROM documents")["n"],
            "ollama_available": llm.ollama_available(), "model": config.OLLAMA_MODEL,
            "retrieval": "hybrid (BM25 + ChromaDB)" if retrieval._dense_ready() else "BM25"}


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, _=Depends(rate_limit)):
    u = db.one("SELECT * FROM users WHERE username=?", (body.username.strip().lower(),))
    if not u or not security.verify_password(body.password, u["password_hash"]):
        db.audit(body.username[:30], "login.failed")
        raise HTTPException(401, "Incorrect username or password")
    db.audit(u["username"], "login.success")
    return {"token": security.make_token(u["username"], u["role"], u["display_name"]),
            "role": u["role"], "display_name": u["display_name"]}


@app.get("/api/services")
def services(q: Optional[str] = None):
    rows = db.rows("SELECT key,name,description,category,department,info_url,contact,last_reviewed FROM services ORDER BY name")
    if q:
        qt = set(tokens(q))
        rows = [r for r in rows if qt & set(tokens(" ".join(str(v) for v in r.values())))]
    return rows


@app.post("/api/classify")
def classify(body: ChatIn, _=Depends(rate_limit)):
    sug = routing.classify(body.question)
    return {"suggestions": [{k: s[k] for k in ("key", "name", "category", "department", "confidence")} for s in sug],
            "notice": "AI-generated routing is a recommendation and will be reviewed by staff."}


@app.post("/api/chat")
def chat(body: ChatIn, _=Depends(rate_limit)):
    q = body.question.strip()
    flags = []
    if retrieval.looks_like_injection(q):
        flags.append("instruction-like text in the question was ignored")
    if body.language not in llm.LANG_NAMES:
        raise HTTPException(422, "Unsupported language")

    if GREETING.match(q) or len(tokens(q)) == 0:
        return {"answer": "Hello! Ask me about a government service, for example a Smart ID, an SRD grant, tax returns, "
                          "UIF or reporting a municipal fault.", "sources": [], "evidence": 0.0, "evidence_label": "n/a",
                "answered": False, "needs_clarification": True, "suggested_services": [], "flags": flags,
                "generated_by": "system", "notices": []}

    passages, evidence, mode = retrieval.search(q)
    suggestions = [{"key": s["key"], "name": s["name"], "department": s["department"]} for s in routing.classify(q)]
    notices = ["GovIntel provides general guidance from approved documents. It cannot decide eligibility; "
               "the responsible department makes all decisions."] if ELIGIBILITY.search(q) else []

    if len(tokens(q)) <= 1 and len(passages) > 1 and len({p["document_id"] for p in passages}) > 1:
        return {"answer": "Could you tell me a little more? For example, which service or situation do you need help with?",
                "sources": [], "evidence": round(evidence, 2), "evidence_label": "low", "answered": False,
                "needs_clarification": True, "suggested_services": suggestions, "flags": flags,
                "generated_by": "system", "notices": notices}

    if not passages or evidence < config.MIN_EVIDENCE:
        db.execute("INSERT INTO chat_log(topic,answered) VALUES(?,0)", (suggestions[0]["name"] if suggestions else "Unclassified",))
        return {"answer": "I don't have enough verified information in my approved sources to answer that reliably. "
                          "Please contact the relevant department through its official channel, or submit an enquiry "
                          "below and a staff member will follow up.",
                "sources": [], "evidence": round(evidence, 2), "evidence_label": "insufficient", "answered": False,
                "needs_clarification": False, "suggested_services": suggestions, "flags": flags,
                "generated_by": "system", "notices": notices}

    answer = llm.generate(q, passages, body.language)
    generated_by = f"ollama:{config.OLLAMA_MODEL}"
    if not answer:
        answer = llm.extractive_answer(q, passages)
        generated_by = "extractive-fallback"
        if body.language != "en":
            notices.append("Local language model unavailable - answer shown in English from the source text.")
    elif body.language != "en":
        notices.append(TRANSLATION_WARNING)
    if not answer:
        answer = "I found related documents but could not extract a clear answer. Please see the sources below."
    label = "high" if evidence >= 0.6 else "medium" if evidence >= 0.38 else "low"
    top = {p["title"] for p in passages}
    db.execute("INSERT INTO chat_log(topic,answered) VALUES(?,1)", (suggestions[0]["name"] if suggestions else next(iter(top)),))
    if any(p["is_synthetic"] for p in passages):
        notices.append("Demo content: sources are synthetic summaries for the hackathon. Always confirm with the official department.")
    return {"answer": answer, "sources": _sources(passages), "evidence": round(evidence, 2), "evidence_label": label,
            "answered": True, "needs_clarification": False, "suggested_services": suggestions, "flags": flags,
            "generated_by": generated_by, "retrieval": mode, "notices": notices}


@app.post("/api/enquiries", status_code=201)
def create_enquiry(body: EnquiryIn, _=Depends(rate_limit)):
    r = routing.best(body.description)
    category = (body.category or r["category"]).strip()
    now = datetime.now().isoformat(timespec="seconds")
    for _i in range(5):
        ref = f"GA-{datetime.now():%Y%m%d}-{secrets.token_hex(3).upper()}"
        if not db.one("SELECT id FROM enquiries WHERE reference_number=?", (ref,)):
            break
    eid = db.execute(
        "INSERT INTO enquiries(reference_number,category,description,suggested_department,routing_confidence,status,"
        "contact_name,contact_detail,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (ref, category, body.description.strip(), r["department"], r["confidence"], "Submitted",
         body.contact_name, body.contact_detail, now, now))
    db.audit("citizen", "enquiry.created", "enquiry", eid, ref)
    return {"id": eid, "reference_number": ref, "status": "Submitted", "category": category,
            "suggested_department": r["department"], "routing_confidence": r["confidence"],
            "notice": "The suggested department is an AI recommendation that staff will review. Keep your reference number."}


@app.get("/api/enquiries/track/{reference}")
def track(reference: str, _=Depends(rate_limit)):
    e = db.one("SELECT reference_number,category,status,created_at,updated_at,confirmed_department,suggested_department "
               "FROM enquiries WHERE reference_number=?", (reference.strip().upper(),))
    if not e:
        raise HTTPException(404, "No enquiry found with that reference number")
    e["department"] = e.pop("confirmed_department") or e.pop("suggested_department")
    e.pop("suggested_department", None)
    return e


@app.get("/api/enquiries")
def list_enquiries(status: Optional[str] = None, category: Optional[str] = None, q: Optional[str] = None,
                   limit: int = 200, user=Depends(security.require_staff)):
    sql, p = "SELECT * FROM enquiries WHERE 1=1", []
    if status:
        sql += " AND status=?"; p.append(status)
    if category:
        sql += " AND category=?"; p.append(category)
    if q:
        sql += " AND (description LIKE ? OR reference_number LIKE ?)"; p += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY created_at DESC LIMIT ?"
    p.append(min(limit, 500))
    return db.rows(sql, p)


@app.patch("/api/enquiries/{eid}")
def update_enquiry(eid: int, body: EnquiryPatch, user=Depends(security.require_staff)):
    e = db.one("SELECT * FROM enquiries WHERE id=?", (eid,))
    if not e:
        raise HTTPException(404, "Enquiry not found")
    if body.status and body.status not in config.STATUSES:
        raise HTTPException(422, f"Status must be one of {config.STATUSES}")
    status = body.status or e["status"]
    dept = body.confirmed_department or e["confirmed_department"]
    notes = e["staff_notes"] or ""
    if body.note:
        notes += f"[{datetime.now():%Y-%m-%d %H:%M}] {user['display_name']}: {body.note.strip()}\n"
    db.execute("UPDATE enquiries SET status=?, confirmed_department=?, staff_notes=?, updated_at=? WHERE id=?",
               (status, dept, notes, datetime.now().isoformat(timespec="seconds"), eid))
    changes = []
    if status != e["status"]:
        changes.append(f"status {e['status']} -> {status}")
    if dept != e["confirmed_department"]:
        changes.append(f"department -> {dept}")
    if body.note:
        changes.append("note added")
    db.audit(user["username"], "enquiry.updated", "enquiry", eid, "; ".join(changes) or "no change")
    return db.one("SELECT * FROM enquiries WHERE id=?", (eid,))


@app.get("/api/dashboard/stats")
def stats(user=Depends(security.require_staff)):
    total = db.one("SELECT COUNT(*) n FROM enquiries")["n"]
    open_ = db.one("SELECT COUNT(*) n FROM enquiries WHERE status NOT IN ('Resolved','Closed')")["n"]
    by_cat = {r["category"] or "Unclassified": r["n"] for r in db.rows(
        "SELECT category, COUNT(*) n FROM enquiries GROUP BY category ORDER BY n DESC")}
    by_status = {s: 0 for s in config.STATUSES}
    by_status.update({r["status"]: r["n"] for r in db.rows("SELECT status, COUNT(*) n FROM enquiries GROUP BY status")})
    start = (datetime.now() - timedelta(days=13)).date()
    per_day = {r["d"]: r["n"] for r in db.rows(
        "SELECT substr(created_at,1,10) d, COUNT(*) n FROM enquiries GROUP BY d")}
    trend = [{"date": str(start + timedelta(days=i)), "enquiries": per_day.get(str(start + timedelta(days=i)), 0)}
             for i in range(14)]
    chat = db.one("SELECT COUNT(*) n, COALESCE(SUM(answered),0) a FROM chat_log")
    return {"total_enquiries": total, "open_enquiries": open_, "by_category": by_cat, "by_status": by_status,
            "trend": trend, "questions_asked": chat["n"], "questions_answered": chat["a"],
            "documents": db.one("SELECT COUNT(*) n FROM documents")["n"],
            "passages": db.one("SELECT COUNT(*) n FROM chunks")["n"]}


@app.get("/api/audit")
def audit_events(limit: int = 50, user=Depends(security.require_staff)):
    return db.rows("SELECT * FROM audit_events WHERE (?='admin' OR action NOT LIKE 'document.%') ORDER BY id DESC LIMIT ?", (user["role"],min(limit, 200)))


@app.get("/api/documents")
def documents(user=Depends(security.require_staff)):
    return db.rows("SELECT d.*, (SELECT COUNT(*) FROM chunks c WHERE c.document_id=d.id) passages "
                   "FROM documents d WHERE d.classification != 'Restricted' OR ?='admin' ORDER BY d.id", (user["role"],))


@app.post("/api/documents/upload", status_code=201)
async def upload_document(file: UploadFile = File(...), title: str = Form(""), department: str = Form(""),
                          source_url: str = Form(""), version: str = Form("1.0"), review_date: str = Form(""),
                          classification: str = Form("Public"), repository: str = Form("Public library"), owner: str = Form("Demo policy team"),
                          policy_key: str = Form(""), status: str = Form("Active"), user=Depends(security.require_admin)):
    if classification not in ("Public","Internal","Restricted") or status not in ("Active","Superseded","Draft") or repository not in ("Public library","SharePoint (simulated)","DMS (simulated)"):
        raise HTTPException(422,"Invalid document metadata")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in config.ALLOWED_UPLOAD_EXT:
        raise HTTPException(415, f"Only {sorted(config.ALLOWED_UPLOAD_EXT)} files are accepted")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(415, "File is not a valid PDF")
    if source_url and not re.match(r"^https?://", source_url):
        raise HTTPException(422, "Source URL must start with http:// or https://")
    meta = {k: v for k, v in {"title": title.strip(), "department": department.strip(), "source_url": source_url.strip(),
                              "version": version.strip(), "review_date": review_date.strip()}.items() if v}
    meta.update(classification=classification, repository=repository, owner=owner, policy_key=policy_key, status=status)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "upload")[:100]
    try:
        return retrieval.ingest_document(safe_name, data, meta, actor=user["username"])
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(422, f"Could not process document: {e}")


@app.delete("/api/documents/{doc_id}")
def remove_document(doc_id: int, user=Depends(security.require_admin)):
    if db.one("SELECT id FROM rules WHERE policy_document=?",(doc_id,)):
        raise HTTPException(409,"Policy is linked to a rule version and must be retained")
    if not retrieval.delete_document(doc_id, user["username"]):
        raise HTTPException(404, "Document not found")
    return {"deleted": doc_id}


from .govintel import router as govintel_router
app.include_router(govintel_router)
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory=str(config.BASE_DIR / "web"), html=True), name="web")
