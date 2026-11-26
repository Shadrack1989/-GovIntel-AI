"""Document ingestion + retrieval.

Default retrieval is BM25 (pure Python, zero setup, deterministic). If USE_CHROMA=on and Ollama can
produce embeddings (e.g. bge-m3), a dense ChromaDB index is built too and results are fused (RRF).
"""
import math
import re
import threading
from collections import Counter
from pathlib import Path

from . import config, db, llm
from .textutil import tokens

_lock = threading.Lock()
_index = None          # cached BM25 index
_chroma = None

INJECTION_PATTERNS = re.compile(
    r"(ignore (all |any |the )?(previous|prior|above) (instructions|prompts?)|disregard .{0,30}instructions|"
    r"you are now|system prompt|reveal .{0,20}(prompt|instructions)|act as (an? )?(admin|developer)|"
    r"</?(system|assistant)>|\bBEGIN (SYSTEM|INSTRUCTIONS)\b)", re.I)


def looks_like_injection(text: str) -> bool:
    return bool(INJECTION_PATTERNS.search(text or ""))


# ---------------------------------------------------------------- parsing
def parse_frontmatter(text: str):
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        text = text[m.end():]
    return meta, text


def extract_pages(filename: str, data: bytes):
    """Return (meta, [(page_number, text), ...])."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        try:
            import pymupdf  # type: ignore
        except ImportError:
            import fitz as pymupdf  # type: ignore
        pages = []
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            for i, page in enumerate(pdf, start=1):
                t = page.get_text().strip()
                if not t:
                    from .govintel import ocr_image
                    from PIL import Image
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(2,2), alpha=False)
                    t, _ = ocr_image(Image.frombytes('RGB',(pix.width,pix.height),pix.samples))
                if t:
                    pages.append((i, t))
        return {}, pages
    if ext == '.docx':
        from docx import Document
        from io import BytesIO
        doc = Document(BytesIO(data))
        parts = [('## ' if p.style.name.startswith('Heading') else '') + p.text for p in doc.paragraphs]
        parts += [' | '.join(c.text for c in row.cells) for table in doc.tables for row in table.rows]
        return {}, [(1, '\n\n'.join(parts))]
    if ext in ('.html','.htm'):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(data, 'html.parser')
        for tag in soup(['script','style','nav','footer']): tag.decompose()
        for tag in soup.find_all(['h1','h2','h3','h4']): tag.insert_before('\n## ')
        return {}, [(1,soup.get_text('\n',strip=True))]
    if ext in ('.png','.jpg','.jpeg'):
        from .govintel import ocr_image
        from PIL import Image
        from io import BytesIO
        t, _ = ocr_image(Image.open(BytesIO(data)))
        return {}, [(1,t)] if t.strip() else []
    text = data.decode("utf-8", errors="replace")
    meta, body = parse_frontmatter(text)
    return meta, [(1, body)]


def chunk_page(page_no: int, text: str):
    """Split into ~CHUNK_WORDS passages, remembering the nearest markdown/heading section."""
    chunks, section, buf, buf_words = [], "", [], 0

    def flush():
        nonlocal buf, buf_words
        if buf:
            chunks.append({"page": page_no, "section": section, "text": " ".join(buf).strip()})
            tail = " ".join(buf).split()[-config.CHUNK_OVERLAP:] if config.CHUNK_OVERLAP else []
            buf, buf_words = ([" ".join(tail)] if tail else []), len(tail)

    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if para.startswith("#"):
            flush_if = bool(buf)
            if flush_if:
                flush()
            buf, buf_words = [], 0
            section = para.lstrip("# ").strip().split("\n")[0]
            rest = "\n".join(para.split("\n")[1:]).strip()
            para = rest
            if not para:
                continue
        para = re.sub(r"\s+", " ", para)
        for sent_group in _split_long(para):
            n = len(sent_group.split())
            if buf_words + n > config.CHUNK_WORDS and buf_words > config.CHUNK_OVERLAP:
                flush()
            buf.append(sent_group)
            buf_words += n
    if buf_words > 0:
        chunks.append({"page": page_no, "section": section, "text": " ".join(buf).strip()})
    return [c for c in chunks if c["text"]]


def _split_long(para: str, limit=None):
    limit = limit or config.CHUNK_WORDS
    words = para.split()
    if len(words) <= limit:
        return [para]
    return [" ".join(words[i:i + limit]) for i in range(0, len(words), limit)]


# ---------------------------------------------------------------- ingest / remove
def ingest_document(filename: str, data: bytes, meta_override=None, actor="system"):
    meta, pages = extract_pages(filename, data)
    meta = {**meta, **(meta_override or {})}
    if not pages:
        raise ValueError("No extractable text found in the document.")
    title = meta.get("title") or Path(filename).stem.replace("_", " ").replace("-", " ").title()
    doc_id = db.execute(
        "INSERT INTO documents(title,department,source_url,version,review_date,filename,is_synthetic,classification,repository,owner,policy_key,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (title, meta.get("department"), meta.get("source_url"), meta.get("version", "1.0"),
         meta.get("review_date"), filename, 1 if str(meta.get("synthetic", "true")).lower() != "false" else 0, meta.get("classification","Public"), meta.get("repository","Public library"), meta.get("owner","Demo policy team"), meta.get("policy_key",""), meta.get("status","Active")))
    n, skipped = 0, 0
    ids = []
    for page_no, text in pages:
        db.execute("INSERT INTO source_pages VALUES(?,?,?)",(doc_id,page_no,text))
        for ch in chunk_page(page_no, text):
            if looks_like_injection(ch["text"]):      # quarantine instruction-like passages
                skipped += 1
                continue
            cid = db.execute("INSERT INTO chunks(document_id,page_number,section,text) VALUES(?,?,?,?)",
                             (doc_id, ch["page"], ch["section"], ch["text"]))
            ids.append((cid, ch["text"], {"document_id": doc_id}))
            n += 1
    db.audit(actor, "document.ingested", "document", doc_id, f"{filename}: {n} passages, {skipped} quarantined")
    invalidate()
    _dense_add(ids)
    return {"id": doc_id, "title": title, "passages": n, "quarantined": skipped}


def delete_document(doc_id: int, actor: str):
    doc = db.one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not doc:
        return False
    ids = [r["id"] for r in db.rows("SELECT id FROM chunks WHERE document_id=?", (doc_id,))]
    db.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
    db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    db.audit(actor, "document.deleted", "document", doc_id, doc["title"])
    invalidate()
    _dense_delete(ids)
    return True


def seed_documents(actor="system"):
    """Load bundled demo documents if the knowledge base is empty."""
    if db.one("SELECT id FROM documents LIMIT 1"):
        return 0
    count = 0
    for p in sorted(config.DOCS_DIR.glob("*.md")):
        ingest_document(p.name, p.read_bytes(), actor=actor)
        count += 1
    return count


# ---------------------------------------------------------------- BM25
class _Index:
    def __init__(self, role="public", historical=False, policy_key=None):
        allowed = {"public":["Public"],"staff":["Public","Internal"],"admin":["Public","Internal","Restricted"]}.get(role,["Public"])
        self.chunks = db.rows(
            "SELECT c.id, c.document_id, c.page_number, c.section, c.text, d.title, d.department, d.source_url, "
            "d.review_date, d.version, d.is_synthetic, d.status, d.classification, d.repository FROM chunks c JOIN documents d ON d.id=c.document_id "
            "WHERE d.classification IN (" + ",".join("?" for _ in allowed) + ")" + ("" if historical else " AND d.status='Active'") + (" AND d.policy_key=?" if policy_key else ""), allowed+([policy_key] if policy_key else []))
        self.toks = [tokens(c["title"] + " " + c["section"] + " " + c["text"]) for c in self.chunks]
        self.N = len(self.chunks)
        self.avgdl = (sum(len(t) for t in self.toks) / self.N) if self.N else 1
        df = Counter()
        for t in self.toks:
            df.update(set(t))
        self.df = df
        self.tf = [Counter(t) for t in self.toks]

    def idf(self, term):
        n = self.df.get(term, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def search(self, query, k):
        q = list(dict.fromkeys(tokens(query)))
        if not q or not self.N:
            return [], 0.0
        k1, b = 1.5, 0.75
        max_idf = math.log(1 + self.N + 0.5)          # idf for an unseen term
        total_mass = sum(self.idf(t) if t in self.df else max_idf for t in q) or 1.0
        scored = []
        for i, tf in enumerate(self.tf):
            dl = len(self.toks[i]) or 1
            s, mass = 0.0, 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    idf = self.idf(t)
                    s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / self.avgdl))
                    mass += idf
            if s > 0:
                scored.append((s, mass / total_mass, i))
        scored.sort(reverse=True)
        out = []
        for s, cov, i in scored[:k]:
            c = dict(self.chunks[i])
            c["score"], c["coverage"] = round(s, 3), round(cov, 3)
            out.append(c)
        return out, (out[0]["coverage"] if out else 0.0)


def invalidate():
    global _index
    with _lock:
        _index = None


def _get_index():
    global _index
    with _lock:
        if _index is None:
            _index = _Index()
        return _index


def search(query: str, k=None, role="public", historical=False, policy_key=None):
    """Return (passages, evidence 0..1, mode)."""
    k = k or config.TOP_K
    idx = _Index(role, historical, policy_key)
    hits, evidence = idx.search(query, k * 2 if _dense_ready() else k)
    mode = "bm25"
    dense = _dense_query(query, k * 2, [c["id"] for c in idx.chunks]) if _dense_ready() and idx.chunks else None
    if dense:
        by_id = {c["id"]: c for c in idx.chunks}
        rank = {}
        for r, h in enumerate(hits):
            rank[h["id"]] = rank.get(h["id"], 0) + 1 / (60 + r)
        for r, cid in enumerate(dense):
            rank[cid] = rank.get(cid, 0) + 1 / (60 + r)
        fused = sorted(rank, key=rank.get, reverse=True)[:k]
        known = {h["id"]: h for h in hits}
        hits = [known.get(cid) or {**by_id[cid], "score": 0.0, "coverage": 0.0} for cid in fused if cid in by_id]
        mode = "hybrid"
    else:
        hits = hits[:k]
    return hits, evidence, mode


# ---------------------------------------------------------------- optional dense (ChromaDB + Ollama embeddings)
def _dense_ready():
    return config.USE_CHROMA == "on" and llm.ollama_available()


def _collection():
    global _chroma
    if _chroma is None:
        import chromadb  # type: ignore
        client = chromadb.PersistentClient(path=str(config.DATA_DIR / "chroma"))
        _chroma = client.get_or_create_collection("govassist", metadata={"hnsw:space": "cosine"})
    return _chroma


def _dense_add(items):
    if not items or not _dense_ready():
        return
    try:
        embs = llm.embed([t for _, t, _ in items])
        if embs:
            _collection().add(ids=[str(i) for i, _, _ in items], embeddings=embs,
                              documents=[t for _, t, _ in items], metadatas=[{**m,"chunk_id":i} for i, _, m in items])
    except Exception as e:  # never break ingestion because of the optional index
        print(f"[govassist] dense indexing skipped: {e}")


def _dense_delete(ids):
    if ids and _dense_ready():
        try:
            _collection().delete(ids=[str(i) for i in ids])
        except Exception as e:
            print(f"[govassist] dense delete skipped: {e}")


def _dense_query(query, k, allowed_ids):
    try:
        emb = llm.embed([query])
        if not emb:
            return None
        res = _collection().query(query_embeddings=emb, n_results=min(k,len(allowed_ids)), where={"chunk_id":{"$in":allowed_ids}})
        return [int(i) for i in res["ids"][0]]
    except Exception as e:
        print(f"[govassist] dense query skipped: {e}")
        return None


def reindex_dense():
    """Rebuild the dense index from the chunks table (call after enabling USE_CHROMA)."""
    if not _dense_ready():
        return 0
    chs = db.rows("SELECT id, document_id, text FROM chunks")
    _dense_add([(c["id"], c["text"], {"document_id": c["document_id"]}) for c in chs])
    return len(chs)
