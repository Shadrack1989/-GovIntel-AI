"""GovAssist AI - Streamlit front end (citizen portal + staff/admin workspace)."""
import os

import pandas as pd
import requests
import streamlit as st

API = os.getenv("GOVASSIST_API_URL", "http://127.0.0.1:8000").rstrip("/")
STATUSES = ["Submitted", "Under Review", "Referred", "Resolved", "Closed"]
LANGS = {"English": "en", "isiZulu": "zu", "isiXhosa": "xh", "Sesotho": "st"}

st.set_page_config(page_title="GovAssist AI", page_icon="🏛️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1100px;}
.ga-banner {background:#fff8e1;border-left:5px solid #f9a825;padding:.6rem .9rem;border-radius:6px;font-size:.88rem;color:#4a3b00;margin-bottom:1rem}
.ga-pill {display:inline-block;padding:.1rem .6rem;border-radius:999px;font-size:.75rem;font-weight:600;margin-right:.3rem}
.ga-high{background:#e3f6e8;color:#1b6b34}.ga-medium{background:#fff3d6;color:#8a5a00}.ga-low,.ga-insufficient{background:#fde6e6;color:#a12626}
.ga-ref {font-size:1.6rem;font-weight:700;letter-spacing:.04em;color:#0b5394}
</style>""", unsafe_allow_html=True)

S = st.session_state
S.setdefault("token", None); S.setdefault("role", None); S.setdefault("name", None)
S.setdefault("chat", []); S.setdefault("prefill_enquiry", "")


# ----------------------------------------------------------------- API helpers
def api(method, path, auth=False, **kw):
    headers = {"Authorization": f"Bearer {S.token}"} if auth and S.token else {}
    try:
        r = requests.request(method, f"{API}{path}", headers=headers, timeout=90, **kw)
    except requests.RequestException:
        st.error(f"Cannot reach the GovAssist API at {API}. Is the backend running?")
        return None
    if r.status_code == 401 and auth:
        S.token = S.role = S.name = None
        st.warning("Your session expired - please sign in again.")
        return None
    if not r.ok:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        st.error(f"{detail}")
        return None
    return r.json()


@st.cache_data(ttl=30)
def get_health():
    try:
        return requests.get(f"{API}/api/health", timeout=3).json()
    except Exception:
        return None


def banner():
    st.markdown('<div class="ga-banner"><b>Prototype for the SITA InnovAIte Hackathon.</b> Uses public/synthetic '
                'information only. GovAssist is not an official government service and cannot make decisions about '
                'eligibility, benefits or applications. Please do not enter sensitive personal information.</div>',
                unsafe_allow_html=True)


# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🏛️ GovAssist AI")
    st.caption("Source-grounded guidance to government services")
    pages = ["Ask GovAssist", "Service directory", "Submit an enquiry", "Track an enquiry"]
    if S.role in ("staff", "admin"):
        pages += ["Staff dashboard", "Enquiry queue", "Audit log"]
    if S.role == "admin":
        pages += ["Knowledge base"]
    pages += ["Staff sign-in" if not S.token else "Sign out"]
    page = st.radio("Navigate", pages, label_visibility="collapsed")
    st.divider()
    lang_label = st.selectbox("Answer language", list(LANGS), help="Non-English answers need a local model and may need confirmation with the department.")
    h = get_health()
    if h:
        st.caption(f"API: online · {h['documents']} documents")
        st.caption(f"Retrieval: {h['retrieval']}")
        st.caption("AI model: " + (f"Ollama · {h['model']}" if h["ollama_available"] else "extractive mode (no local model detected)"))
    else:
        st.caption("API: offline")
    if S.token:
        st.caption(f"Signed in: {S.name}")

banner()


# ----------------------------------------------------------------- citizen pages
def render_answer(m):
    if m.get("evidence_label") not in (None, "n/a"):
        lab = m["evidence_label"]
        st.markdown(f'<span class="ga-pill ga-{lab}">Evidence: {lab}</span>'
                    f'<span style="font-size:.75rem;color:#777">{m.get("generated_by","")}</span>', unsafe_allow_html=True)
    st.markdown(m["content"])
    for n in m.get("notices", []):
        st.info(n, icon="ℹ️")
    for f in m.get("flags", []):
        st.warning(f"Security note: {f}.")
    if m.get("sources"):
        with st.expander(f"Sources ({len(m['sources'])})"):
            for s in m["sources"]:
                loc = f"{s['title']} - {s['section'] or 'general'}, p.{s['page']}"
                st.markdown(f"**[{s['n']}] {loc}**  \n{s['department'] or ''} · reviewed {s['review_date'] or 'n/a'}"
                            + (f" · [official site]({s['url']})" if s.get("url") else "")
                            + (" · _synthetic demo content_" if s.get("synthetic") else ""))
                st.caption(s["excerpt"])
    if m.get("suggested_services") and (not m.get("answered") or m.get("needs_clarification")):
        st.caption("Possibly related services: " + ", ".join(x["name"] for x in m["suggested_services"]))


if page == "Ask GovAssist":
    st.header("Ask about a government service")
    if not S.chat:
        st.write("Try one of these:")
        cols = st.columns(3)
        examples = ["How do I replace a lost ID?", "My SRD grant was declined. What can I do?", "How do I submit my tax return on eFiling?",
                    "Water has been off in my street for days", "I was retrenched, how do I claim UIF?", "How do I register a company?"]
        for i, ex in enumerate(examples):
            if cols[i % 3].button(ex, use_container_width=True, key=f"ex{i}"):
                S.pending_q = ex
    for m in S.chat:
        with st.chat_message(m["role"]):
            if m["role"] == "assistant":
                render_answer(m)
            else:
                st.markdown(m["content"])
    q = st.chat_input("Ask a question in plain language…") or S.pop("pending_q", None)
    if q:
        S.chat.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("Searching approved sources…"):
                r = api("POST", "/api/chat", json={"question": q, "language": LANGS[lang_label]})
            if r:
                msg = {"role": "assistant", "content": r["answer"], **{k: r.get(k) for k in (
                    "sources", "evidence_label", "generated_by", "notices", "flags", "suggested_services", "answered", "needs_clarification")}}
                S.chat.append(msg)
                S.last_unanswered = None if r["answered"] else q
        st.rerun()
    if S.chat and S.chat[-1]["role"] == "assistant":
        c1, c2 = st.columns([1, 1])
        if c1.button("📨 Not what you needed? Create an enquiry", use_container_width=True):
            last_user = next((m["content"] for m in reversed(S.chat) if m["role"] == "user"), "")
            S.prefill_enquiry = last_user
            st.info("Open **Submit an enquiry** in the sidebar - your question has been copied across.")
        if c2.button("🧹 Clear conversation", use_container_width=True):
            S.chat = []
            st.rerun()

elif page == "Service directory":
    st.header("Service directory")
    q = st.text_input("Search services", placeholder="e.g. grant, licence, tax")
    data = api("GET", "/api/services", params={"q": q} if q else None) or []
    for s in data:
        with st.container(border=True):
            st.subheader(s["name"])
            st.write(s["description"])
            st.caption(f"{s['category']} · **{s['department']}** · last reviewed {s['last_reviewed']}")
            st.markdown(f"[Official information]({s['info_url']}) · {s['contact']}")
    if not data:
        st.write("No services match your search.")

elif page == "Submit an enquiry":
    st.header("Submit an enquiry")
    st.write("Describe your question. A staff member will review it and refer it to the right department.")
    desc = st.text_area("What do you need help with?", value=S.prefill_enquiry, height=140, max_chars=2000)
    if desc and len(desc.strip()) >= 10:
        sug = api("POST", "/api/classify", json={"question": desc})
        opts = [s["name"] for s in (sug or {}).get("suggestions", [])]
        cats = {s["name"]: s for s in (sug or {}).get("suggestions", [])}
        if opts:
            st.caption("Suggested service (AI recommendation - staff will confirm):")
            for o in opts:
                st.write(f"• **{o}** → {cats[o]['department']} (confidence {cats[o]['confidence']:.0%})")
        else:
            st.caption("No service matched automatically; staff will triage your enquiry.")
    st.caption("Contact details are optional - leave them blank if you prefer. Use test details for the demo.")
    c1, c2 = st.columns(2)
    name = c1.text_input("Name (optional)", max_chars=80)
    contact = c2.text_input("Email or phone (optional)", max_chars=120)
    if st.button("Submit enquiry", type="primary", disabled=not desc or len(desc.strip()) < 10):
        r = api("POST", "/api/enquiries", json={"description": desc, "contact_name": name or None, "contact_detail": contact or None})
        if r:
            S.prefill_enquiry = ""
            st.success("Enquiry submitted")
            st.markdown(f'Your reference number<div class="ga-ref">{r["reference_number"]}</div>', unsafe_allow_html=True)
            st.write(f"Status: **{r['status']}** · Category: **{r['category']}** · Suggested department: **{r['suggested_department']}**")
            st.caption(r["notice"])

elif page == "Track an enquiry":
    st.header("Track an enquiry")
    ref = st.text_input("Reference number", placeholder="GA-20261121-ABC123")
    if st.button("Check status", disabled=not ref):
        r = api("GET", f"/api/enquiries/track/{ref.strip()}")
        if r:
            st.metric("Status", r["status"])
            st.write(f"Category: **{r['category']}** · Department: **{r['department']}**")
            st.caption(f"Submitted {r['created_at']} · last updated {r['updated_at']}")

# ----------------------------------------------------------------- staff pages
elif page == "Staff sign-in":
    st.header("Staff and administrator sign-in")
    st.caption("Demo accounts: staff / staff123 · admin / admin123 (test accounts only)")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            r = api("POST", "/api/auth/login", json={"username": u, "password": p})
            if r:
                S.token, S.role, S.name = r["token"], r["role"], r["display_name"]
                st.rerun()

elif page == "Sign out":
    S.token = S.role = S.name = None
    st.rerun()

elif page == "Staff dashboard":
    st.header("Staff dashboard")
    d = api("GET", "/api/dashboard/stats", auth=True)
    if d:
        c = st.columns(5)
        c[0].metric("Total enquiries", d["total_enquiries"])
        c[1].metric("Open enquiries", d["open_enquiries"])
        c[2].metric("Chat questions", d["questions_asked"])
        rate = f"{d['questions_answered'] / d['questions_asked']:.0%}" if d["questions_asked"] else "n/a"
        c[3].metric("Answered with sources", rate)
        c[4].metric("Documents / passages", f"{d['documents']} / {d['passages']}")
        l, r = st.columns(2)
        with l:
            st.subheader("Enquiries by category")
            st.bar_chart(pd.Series(d["by_category"], name="Enquiries"))
        with r:
            st.subheader("Enquiries by status")
            st.bar_chart(pd.Series(d["by_status"], name="Enquiries"))
        st.subheader("Enquiries per day (last 14 days)")
        st.line_chart(pd.DataFrame(d["trend"]).set_index("date"))
        st.caption("Dashboard figures include synthetic seed data for demonstration.")

elif page == "Enquiry queue":
    st.header("Enquiry queue")
    f1, f2, f3 = st.columns([2, 1, 1])
    q = f1.text_input("Search", placeholder="reference or keyword")
    sf = f2.selectbox("Status", ["All"] + STATUSES)
    params = {k: v for k, v in {"q": q, "status": None if sf == "All" else sf}.items() if v}
    data = api("GET", "/api/enquiries", auth=True, params=params)
    if data is not None:
        df = pd.DataFrame(data)
        if df.empty:
            st.write("No enquiries match.")
        else:
            view = df[["id", "reference_number", "created_at", "category", "status", "suggested_department"]]
            ev = st.dataframe(view, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
            idx = ev.selection.rows[0] if ev.selection.rows else 0
            e = data[idx]
            st.divider()
            st.subheader(f"{e['reference_number']}")
            st.write(e["description"])
            st.caption(f"Contact: {e.get('contact_name') or '-'} / {e.get('contact_detail') or '-'} · "
                       f"AI-suggested: **{e['suggested_department']}** (confidence {e['routing_confidence'] or 0:.0%}) - recommendation, needs staff review")
            if e.get("staff_notes"):
                st.text(e["staff_notes"])
            with st.form(f"upd{e['id']}"):
                a, b = st.columns(2)
                new_status = a.selectbox("Status", STATUSES, index=STATUSES.index(e["status"]))
                dept = b.text_input("Confirmed department", value=e["confirmed_department"] or e["suggested_department"] or "")
                note = st.text_area("Internal note", max_chars=1000)
                if st.form_submit_button("Save changes", type="primary"):
                    r = api("PATCH", f"/api/enquiries/{e['id']}", auth=True,
                            json={"status": new_status, "confirmed_department": dept, "note": note or None})
                    if r:
                        st.success("Saved and recorded in the audit log")
                        st.rerun()

elif page == "Audit log":
    st.header("Recent audit events")
    data = api("GET", "/api/audit", auth=True, params={"limit": 100})
    if data:
        st.dataframe(pd.DataFrame(data)[["timestamp", "actor", "action", "record_type", "record_id", "detail"]],
                     use_container_width=True, hide_index=True)

elif page == "Knowledge base":
    st.header("Knowledge base (administrator)")
    docs = api("GET", "/api/documents", auth=True)
    if docs:
        st.dataframe(pd.DataFrame(docs)[["id", "title", "department", "version", "review_date", "status", "passages"]],
                     use_container_width=True, hide_index=True)
        with st.expander("Remove a document"):
            did = st.selectbox("Document", [d["id"] for d in docs], format_func=lambda i: next(d["title"] for d in docs if d["id"] == i))
            if st.button("Delete document and its passages"):
                if api("DELETE", f"/api/documents/{did}", auth=True):
                    st.success("Deleted")
                    st.rerun()
    st.subheader("Add an approved document")
    st.caption("PDF, TXT or MD up to 5 MB. Public or synthetic content only - never upload confidential or personal information.")
    with st.form("upload", clear_on_submit=True):
        up = st.file_uploader("File", type=["pdf", "txt", "md"])
        c1, c2 = st.columns(2)
        title = c1.text_input("Title"); dept = c2.text_input("Department")
        c3, c4, c5 = st.columns(3)
        url = c3.text_input("Official source URL"); ver = c4.text_input("Version", value="1.0"); rev = c5.text_input("Review date (YYYY-MM-DD)")
        if st.form_submit_button("Upload and index", type="primary") and up:
            r = api("POST", "/api/documents/upload", auth=True, files={"file": (up.name, up.getvalue())},
                    data={"title": title, "department": dept, "source_url": url, "version": ver, "review_date": rev})
            if r:
                st.success(f"Indexed '{r['title']}': {r['passages']} passages ({r['quarantined']} quarantined as instruction-like).")
