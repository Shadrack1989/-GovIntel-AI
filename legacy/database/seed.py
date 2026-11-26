"""First-run seeding: demo users, sample documents and SYNTHETIC enquiries. No real citizen data."""
import random
from datetime import datetime, timedelta, timezone

from backend import config
from backend.database.db import audit, get_db
from backend.security.auth import hash_password
from backend.services import document_service, routing_service

SYNTHETIC_ENQUIRIES = [
    ("Identity documents", "My Smart ID application has been pending for weeks and I have not received an SMS."),
    ("Identity documents", "My ID was stolen last week. What must I do before I can apply again?"),
    ("Birth registration", "I need to register my newborn but the hospital did not give me a notification form."),
    ("Birth registration", "Late registration of birth for my nephew who is 9 years old."),
    ("Social grants", "My child support grant payment did not reflect this month."),
    ("Social grants", "I applied for a disability grant and was asked for a medical assessment. Where do I go?"),
    ("Social grants", "How do I check the status of my SRD application?"),
    ("Driving licence", "My driving licence card expired two months ago. Can I still renew it?"),
    ("Driving licence", "I cannot find a licensing centre with an available booking slot."),
    ("Municipal services", "I was charged for water but my meter shows much lower usage. I want to dispute the bill."),
    ("Municipal services", "There has been no electricity in our street for two days."),
    ("Municipal services", "Refuse has not been collected for two weeks."),
    ("Tax (SARS)", "I forgot my eFiling password and cannot receive the OTP."),
    ("Tax (SARS)", "I disagree with my assessment and want to object."),
    ("Complaints & escalation", "I have been bounced between offices and nobody gives me a reference number."),
    ("General enquiry", "Which department handles the registration of a small business?"),
]


def seed_if_empty() -> None:
    with get_db() as db:
        has_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        has_docs = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        has_enq = db.execute("SELECT COUNT(*) FROM enquiries").fetchone()[0]
        if not has_users:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            for u in config.DEMO_USERS:
                db.execute("INSERT INTO users(username,display_name,role,password_hash,created_at) VALUES(?,?,?,?,?)",
                           (u["username"], u["display_name"], u["role"], hash_password(u["password"]), now))
    if not has_docs:
        document_service.load_sample_documents()
    if not has_enq:
        rng = random.Random(2026)
        now = datetime.now(timezone.utc)
        statuses = ["Submitted"] * 5 + ["Under Review"] * 4 + ["Referred"] * 3 + ["Resolved"] * 3 + ["Closed"] * 2
        with get_db() as db:
            for i in range(34):
                category, desc = SYNTHETIC_ENQUIRIES[i % len(SYNTHETIC_ENQUIRIES)]
                route = routing_service.classify(desc)
                created = now - timedelta(days=rng.randint(0, 13), hours=rng.randint(0, 20), minutes=rng.randint(0, 59))
                stamp = created.strftime("%Y-%m-%dT%H:%M:%SZ")
                ref = f"GA-{rng.randrange(10**7, 10**8)}".replace("0", "K").replace("1", "L")
                db.execute(
                    "INSERT INTO enquiries(reference_number,category,description,suggested_department,"
                    "routing_confidence,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (ref, route["category"] if route["service_id"] else category, desc, route["department"],
                     route["confidence"], rng.choice(statuses), stamp, stamp),
                )
            audit(db, "system", "seed.enquiries", "enquiry", "-", "34 synthetic demonstration enquiries")
