"""Document intelligence: extraction, chunking, safety scanning and ingestion."""
import re
from pathlib import Path

from backend import config
from backend.database.db import audit, get_db, now_iso

# Retrieved/uploaded text is DATA, never instructions. Reject documents that try to give orders to the model.
INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts|rules)",
    r"disregard (all |any |the )?(previous|prior|above|earlier)",
    r"you are now\b",
    r"system prompt",
    r"reveal (your|the) (instructions|prompt|password|secret)",
    r"act as (an? )?(unrestricted|jailbroken|different)",
    r"do not (tell|inform) the user",
]
_INJ = re.compile("|".join(INJECTION_PATTERNS), re.I)

STEP_HEADING = re.compile(r"how to|steps?\b|process|apply|register|dispute|report|escalat|renew|check", re.I)
NEED_HEADING = re.compile(r"what you (may )?need|requirements?|documents?|checklist|bring", re.I)


def looks_like_injection(text: str) -> bool:
    return bool(_INJ.search(text))


def section_kind(heading: str) -> str:
    h = heading or ""
    if NEED_HEADING.search(h):
        return "needs"
    if STEP_HEADING.search(h):
        return "steps"
    return "info"


def parse_front_matter(text: str) -> tuple[dict, str]:
    meta: dict = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
            text = text[end + 4:].lstrip("\n")
    return meta, text


def extract_pages(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    ext = Path(filename).suffix.lower()
    if ext in (".txt", ".md"):
        return [(None, data.decode("utf-8", errors="replace"))]
    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF (preferred, as in the proposal)
            with fitz.open(stream=data, filetype="pdf") as pdf:
                return [(i + 1, p.get_text()) for i, p in enumerate(pdf)]
        except ImportError:
            pass
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
        except ImportError as exc:
            raise ValueError("PDF support needs 'pymupdf' or 'pypdf' installed.") from exc
        except Exception as exc:
            raise ValueError("That PDF could not be read.") from exc
    raise ValueError("Unsupported file type.")


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown-ish text into (heading, body) sections."""
    sections, heading, buf = [], "", []
    for line in text.splitlines():
        m = re.match(r"^#{1,4}\s+(.*\S)\s*$", line)
        if m:
            if "".join(buf).strip():
                sections.append((heading, "\n".join(buf).strip()))
            heading, buf = m.group(1), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append((heading, "\n".join(buf).strip()))
    return sections


def chunk_pages(pages: list[tuple[int | None, str]], max_chars: int = 900) -> list[dict]:
    chunks = []
    for page_no, text in pages:
        for heading, body in _split_sections(text):
            paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
            cur = ""
            for p in paras:
                if cur and len(cur) + len(p) > max_chars:
                    chunks.append({"page_number": page_no, "section": heading, "text": cur})
                    cur = p
                else:
                    cur = f"{cur}\n\n{p}".strip()
            if cur:
                chunks.append({"page_number": page_no, "section": heading, "text": cur})
    for c in chunks:
        c["kind"] = section_kind(c["section"])
    return chunks


def ingest(filename: str, data: bytes, actor: str, overrides: dict | None = None) -> dict:
    """Validate, chunk and store a document. Raises ValueError with a user-safe message."""
    ext = Path(filename).suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise ValueError(f"Only {', '.join(sorted(config.ALLOWED_EXTENSIONS))} files are accepted.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ValueError("File is too large (limit 5 MB).")
    pages = extract_pages(filename, data)
    if ext in (".txt", ".md"):
        meta, body = parse_front_matter(pages[0][1])
        pages = [(None, body)]
    else:
        meta = {}
    meta.update({k: v for k, v in (overrides or {}).items() if v})
    full_text = "\n".join(t for _, t in pages)
    if len(full_text.strip()) < 50:
        raise ValueError("No readable text found in that document (scanned PDFs need OCR first).")
    if looks_like_injection(full_text):
        with get_db() as db:
            audit(db, actor, "document.rejected", "document", "-", f"{filename}: possible prompt-injection content")
        raise ValueError("Upload rejected: the document contains text that tries to instruct the AI "
                         "(possible prompt injection). Review the file and try again.")
    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError("The document produced no searchable passages.")
    title = meta.get("title") or Path(filename).stem.replace("_", " ").replace("-", " ").title()
    with get_db() as db:
        # Replacement: an earlier Active document with the same title is superseded.
        old = db.execute("SELECT id FROM documents WHERE title=? AND status='Active'", (title,)).fetchall()
        for o in old:
            db.execute("DELETE FROM chunks WHERE document_id=?", (o["id"],))
            db.execute("UPDATE documents SET status='Superseded' WHERE id=?", (o["id"],))
        cur = db.execute(
            "INSERT INTO documents(title,department,service_id,source_url,version,review_date,status,filename,"
            "synthetic,chunk_count,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (title, meta.get("department", "Unspecified department"), meta.get("service"),
             meta.get("source_url"), meta.get("version", "1.0"), meta.get("review_date"), "Active",
             filename, 0 if str(meta.get("synthetic", "true")).lower() == "false" else 1, len(chunks), now_iso()),
        )
        doc_id = cur.lastrowid
        db.executemany(
            "INSERT INTO chunks(document_id,page_number,section,kind,text) VALUES(?,?,?,?,?)",
            [(doc_id, c["page_number"], c["section"], c["kind"], c["text"]) for c in chunks],
        )
        audit(db, actor, "document.replaced" if old else "document.added", "document", doc_id,
              f"{title} ({len(chunks)} passages)")
    return {"id": doc_id, "title": title, "chunks": len(chunks), "replaced": len(old)}


def remove(doc_id: int, actor: str) -> bool:
    with get_db() as db:
        row = db.execute("SELECT title FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not row:
            return False
        db.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
        db.execute("UPDATE documents SET status='Removed', chunk_count=0 WHERE id=?", (doc_id,))
        audit(db, actor, "document.removed", "document", doc_id, row["title"])
    return True


def load_sample_documents(actor: str = "system") -> int:
    n = 0
    for path in sorted(config.SAMPLE_DOCS_DIR.glob("*.md")):
        ingest(path.name, path.read_bytes(), actor)
        n += 1
    return n
