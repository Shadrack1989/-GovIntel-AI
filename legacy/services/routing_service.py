"""Controlled routing directory + enquiry classification.

Routing output is ALWAYS a recommendation for staff review, never a decision.
"""
import json
from functools import lru_cache

from backend import config
from backend.services.rag_service import stem, tokenize

GENERAL = {
    "category": "General enquiry",
    "service_id": None,
    "department": "Needs staff triage",
    "department_url": "https://www.gov.za",
}


@lru_cache(maxsize=1)
def load_services() -> list[dict]:
    with open(config.SERVICES_FILE, encoding="utf-8") as fh:
        services = json.load(fh)
    for s in services:
        s["_kw"] = [[stem(t) for t in tokenize(k)] for k in s["keywords"]]
    return services


def public_services() -> list[dict]:
    return [{k: v for k, v in s.items() if not k.startswith("_")} for s in load_services()]


def get_service(service_id: str | None) -> dict | None:
    return next((s for s in load_services() if s["id"] == service_id), None)


def classify(text: str) -> dict:
    stems = {stem(t) for t in tokenize(text)}
    scored = []
    for s in load_services():
        score = 0
        matched = []
        for kw_stems, kw in zip(s["_kw"], s["keywords"]):
            if kw_stems and all(k in stems for k in kw_stems):
                score += len(kw_stems)  # multi-word keywords count for more
                matched.append(kw)
        if score:
            scored.append((score, s, matched))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return {**GENERAL, "confidence": "low", "matched": [], "note": ROUTING_NOTE}
    top_score, top, matched = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0
    if top_score >= 2 and top_score > second:
        conf = "high"
    elif top_score > second:
        conf = "medium"
    else:
        conf = "low"
    return {
        "category": top["category"], "service_id": top["id"], "department": top["department"],
        "department_url": top["department_url"], "confidence": conf, "matched": matched, "note": ROUTING_NOTE,
    }


ROUTING_NOTE = "AI-generated suggestion. A staff member will review it before the enquiry is referred."
