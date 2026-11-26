"""Retrieval service: BM25 keyword retrieval with light stemming and synonym expansion.

Pure Python, no model download, so the prototype runs anywhere. The interface (`search`) is the
seam where an embedding model (e.g. BGE-M3) plus a vector store (ChromaDB) can be dropped in
without touching the API layer.
"""
import math
import re
import threading
from collections import Counter

from backend.database.db import get_db

STOPWORDS = set("""
a an and are as at be been but by can could did do does doing for from get got had has have how i if in into is it
its me my of on or our please so some than that the their them then there these they this to us was we were what
when where which who why will with would you your am im ive hi hello hey thanks thank help want need needs like know
tell about just also any not no yes should shall may might must much many very more most other new next
""".split())

SYNONYM_GROUPS = [
    ["id", "identity", "identification"],
    ["licence", "license", "licensing"],
    ["bill", "invoice", "account", "statement", "charges"],
    ["electricity", "power", "eskom", "outage", "blackout", "lights"],
    ["water", "leak", "burst", "pipe"],
    ["refuse", "rubbish", "waste", "garbage", "trash"],
    ["grant", "sassa", "allowance", "srd"],
    ["tax", "sars", "efiling", "revenue"],
    ["birth", "born", "baby", "newborn"],
    ["child", "children", "kid", "kids"],
    ["complaint", "complain", "escalate", "escalation", "grievance"],
    ["cost", "price", "fee", "fees", "pay", "payment", "paid"],
    ["renew", "renewal", "expire", "expired", "expiry"],
    ["lost", "stolen", "missing", "replace", "replacement"],
    ["document", "documents", "papers", "paperwork"],
    ["delay", "delayed", "waiting", "slow", "stuck"],
    ["driver", "driving", "drive"],
    ["dispute", "disagree", "wrong", "incorrect", "error", "query"],
]

_SUFFIXES = ("ations", "ation", "ings", "ing", "ions", "ion", "ers", "er", "ed", "es", "s")


def stem(word: str) -> str:
    w = word.lower()
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    if w.endswith("y") and len(w) > 3:
        w = w[:-1] + "i"
    return w[:5]


_SYN: dict[str, set[str]] = {}
for _grp in SYNONYM_GROUPS:
    _stems = {stem(w) for w in _grp}
    for _w in _grp:
        _SYN.setdefault(stem(_w), set()).update(_stems)


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def query_terms(query: str) -> list[tuple[str, set[str]]]:
    """Return [(stem, {alternative stems})] for each distinct significant word in the query."""
    seen, out = set(), []
    for tok in tokenize(query):
        s = stem(tok)
        if s in seen or len(tok) < 2:
            continue
        seen.add(s)
        out.append((s, _SYN.get(s, set()) - {s}))
    return out


class KnowledgeBase:
    K1, B = 1.5, 0.75

    def __init__(self):
        self._lock = threading.Lock()
        self.chunks: list[dict] = []
        self._tf: list[Counter] = []
        self._len: list[int] = []
        self._df: Counter = Counter()
        self._avgdl = 1.0

    def rebuild(self) -> int:
        with get_db() as db:
            rows = db.execute(
                "SELECT c.id,c.document_id,c.page_number,c.section,c.kind,c.text,"
                "d.title,d.department,d.service_id,d.source_url,d.version,d.review_date,d.synthetic "
                "FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.status='Active'"
            ).fetchall()
        chunks = [dict(r) for r in rows]
        tfs, lens, df = [], [], Counter()
        for c in chunks:
            # Title and section heading are searchable too: they carry strong topical signal.
            toks = [stem(t) for t in tokenize(f"{c['title']} {c['section'] or ''} {c['text']}")]
            tf = Counter(toks)
            tfs.append(tf)
            lens.append(len(toks))
            df.update(tf.keys())
        with self._lock:
            self.chunks, self._tf, self._len, self._df = chunks, tfs, lens, df
            self._avgdl = (sum(lens) / len(lens)) if lens else 1.0
        return len(chunks)

    def _idf(self, s: str) -> float:
        n = len(self.chunks)
        d = self._df.get(s, 0)
        return math.log(1 + (n - d + 0.5) / (d + 0.5))

    def _term_score(self, i: int, stems: set[str]) -> tuple[float, bool]:
        best, hit = 0.0, False
        for j, s in enumerate(stems):
            f = self._tf[i].get(s, 0)
            if not f:
                continue
            hit = True
            norm = f * (self.K1 + 1) / (f + self.K1 * (1 - self.B + self.B * self._len[i] / self._avgdl))
            best = max(best, self._idf(s) * norm)
        return best, hit

    def search(self, query: str, k: int = 6) -> tuple[list[dict], list[str]]:
        """Return (ranked chunks with score + matched_terms, list of query term stems)."""
        terms = query_terms(query)
        if not terms or not self.chunks:
            return [], [t for t, _ in terms]
        results = []
        for i, chunk in enumerate(self.chunks):
            score, matched = 0.0, []
            for s, alts in terms:
                ts, hit = self._term_score(i, {s})
                if not hit and alts:
                    ts, hit = self._term_score(i, alts)
                    ts *= 0.7
                if hit:
                    score += ts
                    matched.append(s)
            if matched:
                results.append({**chunk, "score": round(score, 3), "matched_terms": matched})
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:k], [t for t, _ in terms]


kb = KnowledgeBase()
