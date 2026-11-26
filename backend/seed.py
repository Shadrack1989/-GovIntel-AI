"""Seed demo users, services, documents and synthetic enquiries (idempotent)."""
import json
import random
from datetime import datetime, timedelta

from . import config, db, retrieval, routing, security

SYNTHETIC_ENQUIRIES = [
    "I lost my ID and need to know how to replace it.", "My SRD grant status says declined, what can I do?",
    "How do I register my newborn baby's birth?", "Water has been off in my street for three days.",
    "I cannot log in to eFiling to submit my tax return.", "How do I renew my driving licence card?",
    "I was retrenched and want to claim UIF.", "How do I register a company for my startup?",
    "There is a large pothole on our road causing accidents.", "My municipal bill looks wrong, I want to query it.",
    "Where can I apply for a Smart ID?", "My tax refund has not been paid yet.",
    "I need a late registration of birth for my child.", "SASSA grant payment has not arrived.",
    "How do I submit annual returns for my company?", "Electricity outage in my area for two days.",
    "Employer has not paid UIF contributions for me.", "Need my driver's licence booking for an eye test.",
]


def run():
    db.init_db()
    for username, name, role, pw in config.DEMO_USERS:
        if not db.one("SELECT id FROM users WHERE username=?", (username,)):
            db.execute("INSERT INTO users(username,display_name,role,password_hash) VALUES(?,?,?,?)",
                       (username, name, role, security.hash_password(pw)))
    if not db.one("SELECT id FROM services LIMIT 1"):
        for s in json.loads((config.DATA_DIR / "services.json").read_text(encoding="utf-8")):
            db.execute("INSERT INTO services(key,name,description,category,department,info_url,contact,keywords,last_reviewed)"
                       " VALUES(?,?,?,?,?,?,?,?,?)",
                       (s["key"], s["name"], s["description"], s["category"], s["department"], s["info_url"],
                        s["contact"], s["keywords"], s["last_reviewed"]))
    retrieval.seed_documents()
    if not db.one("SELECT id FROM enquiries LIMIT 1"):
        rnd = random.Random(26)
        statuses = config.STATUSES
        weights = [4, 3, 3, 4, 2]
        now = datetime.now()
        for i in range(34):
            text = rnd.choice(SYNTHETIC_ENQUIRIES)
            r = routing.best(text)
            created = now - timedelta(days=rnd.randint(0, 27), hours=rnd.randint(0, 20))
            ref = f"GA-{created:%Y%m%d}-{1000 + i}"
            st = rnd.choices(statuses, weights)[0]
            db.execute(
                "INSERT INTO enquiries(reference_number,category,description,suggested_department,routing_confidence,status,"
                "contact_name,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (ref, r["category"], text, r["department"], r["confidence"], st, "Synthetic Citizen",
                 created.isoformat(timespec="seconds"), created.isoformat(timespec="seconds")))
