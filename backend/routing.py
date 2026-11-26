"""Controlled routing directory: keyword scoring over the services table.
Output is always a RECOMMENDATION that staff must confirm."""
from . import db
from .textutil import tokens

FALLBACK = {"key": None, "name": "Unclassified", "category": "General", "department": "Unassigned - staff to triage"}


def classify(text: str, top=3):
    q = set(tokens(text))
    ranked = []
    for s in db.rows("SELECT * FROM services"):
        kw = set(tokens(s["keywords"] + " " + s["name"]))
        hit = q & kw
        score = len(hit) / (len(hit) + 1.5) if hit else 0.0   # saturating confidence in 0..1
        if score > 0:
            ranked.append({**s, "confidence": round(score, 2), "matched": sorted(hit)})
    ranked.sort(key=lambda r: -r["confidence"])
    return ranked[:top]


def best(text: str):
    r = classify(text, 1)
    return r[0] if r else {**FALLBACK, "confidence": 0.0, "matched": []}
