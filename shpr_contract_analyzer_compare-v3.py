# app_contract_analyzer_two_tabs_llm_both.py
# Streamlit app — Two tabs, both LLM-only
# Tab 1: Analyze one contract (LLM JSON: key_clauses, risks, recommendations)
# Tab 2: Compare two contracts (LLM JSON: major_changes, overall_assessment, should_renegotiate, key_points_to_verify)

import os
import io
import json
from typing import List, Dict, Any
from datetime import datetime, timedelta

import streamlit as st

# Optional text extractors (no table parsing; LLM-only analysis)
_PDF_OK = True
try:
    import pdfplumber
except Exception:
    _PDF_OK = False

_DOCX_OK = True
try:
    import docx  # python-docx
except Exception:
    _DOCX_OK = False

try:
    from groq import Groq
    _GROQ_OK = True
except Exception:
    _GROQ_OK = False

# ------------------ App setup ------------------
st.set_page_config(page_title="Shopper AI Contract Analyzer & Vergelijker", page_icon="📄", layout="wide")

# ------------------ AUTH (demo) ------------------
# Simple session-gated login for demo purposes. Replace with proper auth for production.
DEMO_USERS = {
    "demo": "letmein123",
    "sandeep": "secret123",
}
IDLE_TIMEOUT_MIN = 60  # auto-logout after inactivity

def login_form():
    st.title("🔐 Login")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
        if submitted:
            if u in DEMO_USERS and DEMO_USERS[u] == p:
                st.session_state.authenticated = True
                st.session_state.username = u
                st.session_state.last_active = datetime.utcnow()
                st.rerun()
            else:
                st.error("Invalid username or password")

def ensure_authenticated():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "last_active" not in st.session_state:
        st.session_state.last_active = None

    # idle timeout
    if st.session_state.authenticated and st.session_state.last_active:
        if datetime.utcnow() - st.session_state.last_active > timedelta(minutes=IDLE_TIMEOUT_MIN):
            st.session_state.clear()
            st.warning("Session timed out. Please sign in again.")
            st.rerun()

    if not st.session_state.authenticated:
        login_form()
        st.stop()

    # update last activity
    st.session_state.last_active = datetime.utcnow()

def top_bar():
    left, right = st.columns([4,1])
    with right:
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()
    st.caption(f"Signed in as **{st.session_state.get('username','')}**")

# Gate the whole app below this line
ensure_authenticated()

st.title("📄 Shopper AI Contract Analyzer & Vergelijker")

models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]
model_name = st.sidebar.selectbox("Groq model", models, index=0)
lang = st.sidebar.selectbox("Language / Taal", ["English", "Nederlands"], index=1)
NL = lang == "Nederlands"
top_bar()

def T(nl: str, en: str) -> str:
    return nl if NL else en

# ---------- File reading (text only) ----------
def read_file_to_text(upload) -> str:
    name = (upload.name or "").lower()
    raw = upload.read()
    if name.endswith(".pdf") and _PDF_OK:
        try:
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                return "\n\n".join([p.extract_text() or "" for p in pdf.pages])
        except Exception:
            pass
    if name.endswith(".docx") and _DOCX_OK:
        try:
            d = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in d.paragraphs)
        except Exception:
            pass
    try:
        return raw.decode("utf-8")
    except Exception:
        return raw.decode(errors="ignore")

# ---------- Prompts ----------
PROMPT_ANALYZE_EN = (
    """
You are a legal AI assistant. Analyze the contract and return ONLY JSON:
{
  "key_clauses": ["plain-language key clauses (max 5)"],
  "risks": ["plain-language top risks (max 5)"],
  "recommendations": ["plain-language next steps (max 5)"]
}
Text:\n"""
)

PROMPT_ANALYZE_NL = (
    """
Je bent een juridisch AI-assistent. Analyseer het contract en geef ALLEEN JSON terug:
{
  "key_clauses": ["belangrijkste clausules in gewone taal (max 5)"],
  "risks": ["grootste risico's (max 5)"],
  "recommendations": ["volgende stappen/adviezen (max 5)"]
}
Tekst:\n"""
)

PROMPT_COMPARE_EN = (
    """
You are a legal AI. Compare TWO contract texts (A=old, B=new). Return ONLY JSON:
{
  "major_changes": [
    {"type": "clause|risk|recommendation", "change": "added|removed|modified|tightened|loosened",
     "title": "short label", "before": "snippet A", "after": "snippet B",
     "impact": "low|medium|high", "note": "plain language"}
  ],
  "overall_assessment": "plain language summary",
  "should_renegotiate": true,
  "key_points_to_verify": ["bullets"],
  "pricing_compare": {
    "totals": {
      "currency": "EUR|USD|…",
      "one_time": {"old": null, "new": null, "delta": null},
      "monthly":  {"old": null, "new": null, "delta": null},
      "yearly":   {"old": null, "new": null, "delta": null}
    },
    "items_added": [
      {"description": "string", "qty": 1.0, "unit": "user|month|year|one-time|…",
       "unit_price": 0.0, "currency": "EUR|USD|…", "period": "one-time|monthly|yearly|per-use|other",
       "line_total": 0.0}
    ],
    "items_removed": [
      {"description": "string"}
    ],
    "items_modified": [
      {"description": "string", "fields_changed": {"qty": {"old": 0, "new": 0}, "unit_price": {"old": 0.0, "new": 0.0}, "period": {"old": "", "new": ""}, "line_total": {"old": 0.0, "new": 0.0}}}
    ],
    "price_changes": {
      "old": [{"type": "increase|decrease|indexation|discount_end|other", "amount": 0.0, "percent": 0.0, "currency": "EUR", "effective_date": "YYYY-MM-DD", "note": "..."}],
      "new": [{"type": "increase|decrease|indexation|discount_end|other", "amount": 0.0, "percent": 0.0, "currency": "EUR", "effective_date": "YYYY-MM-DD", "note": "..."}],
      "diff_summary": "plain-language summary of pricing rule differences"
    },
    "indexation": {
      "old": {"method": "CPI|CPI+X|none|other", "cap": 0.0, "floor": 0.0, "frequency": "annual|other"},
      "new": {"method": "CPI|CPI+X|none|other", "cap": 0.0, "floor": 0.0, "frequency": "annual|other"}
    }
  }
}
Rules:
- Include the "pricing_compare" object **only if** pricing/fees/amounts/tables, price changes, or indexation appear in either A or B. Otherwise omit the field entirely.
- Do **not** invent numbers. If a value is not stated, set it to null or omit that leaf field.
- Keep responses concise and JSON-valid. No extra text.

Respond only with JSON.
"""
)

PROMPT_COMPARE_NL = (
    """
Je bent een juridische AI. Vergelijk TWEE contractteksten (A=oud, B=nieuw). Geef ALLEEN JSON terug:
{
  "major_changes": [
    {"type": "clause|risk|recommendation", "change": "added|removed|modified|tightened|loosened",
     "title": "korte titel", "before": "fragment A", "after": "fragment B",
     "impact": "low|medium|high", "note": "uitleg in gewone taal"}
  ],
  "overall_assessment": "samenvatting in gewone taal",
  "should_renegotiate": true,
  "key_points_to_verify": ["bullets"],
  "pricing_compare": {
    "totals": {
      "currency": "EUR|USD|…",
      "one_time": {"old": null, "new": null, "delta": null},
      "monthly":  {"old": null, "new": null, "delta": null},
      "yearly":   {"old": null, "new": null, "delta": null}
    },
    "items_added": [
      {"description": "string", "qty": 1.0, "unit": "gebruiker|maand|jaar|eenmalig|…",
       "unit_price": 0.0, "currency": "EUR|USD|…", "period": "eenmalig|maandelijks|jaarlijks|per-gebruik|overig",
       "line_total": 0.0}
    ],
    "items_removed": [
      {"description": "string"}
    ],
    "items_modified": [
      {"description": "string", "fields_changed": {"qty": {"old": 0, "new": 0}, "unit_price": {"old": 0.0, "new": 0.0}, "period": {"old": "", "new": ""}, "line_total": {"old": 0.0, "new": 0.0}}}
    ],
    "price_changes": {
      "old": [{"type": "increase|decrease|indexation|discount_end|other", "amount": 0.0, "percent": 0.0, "currency": "EUR", "effective_date": "YYYY-MM-DD", "note": "..."}],
      "new": [{"type": "increase|decrease|indexation|discount_end|other", "amount": 0.0, "percent": 0.0, "currency": "EUR", "effective_date": "YYYY-MM-DD", "note": "..."}],
      "diff_summary": "korte samenvatting van verschillen in prijsregels"
    },
    "indexation": {
      "old": {"method": "CPI|CPI+X|geen|overig", "cap": 0.0, "floor": 0.0, "frequency": "jaarlijks|overig"},
      "new": {"method": "CPI|CPI+X|geen|overig", "cap": 0.0, "floor": 0.0, "frequency": "jaarlijks|overig"}
}
  }
}
Regels:
- Voeg het object "pricing_compare" **alleen toe** als er in A of B prijzen/kosten/bedragen/tabellen, prijswijzigingen of indexatie voorkomen. Anders het veld weglaten.
- Geen getallen verzinnen. Als iets niet staat vermeld: gebruik null of laat het veld weg.
- Antwoord kort en als geldige JSON. Geen extra tekst.

Antwoord alleen met JSON.
"""
)

# ---------- Groq calls ----------
def _groq_client() -> Groq:
    # Protect your key: set it in Streamlit Secrets on Community Cloud
    # (App -> Settings -> Secrets): GROQ_API_KEY = "xxx"
    # Local dev can use environment variable as fallback.
    api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    if not _GROQ_OK or not api_key:
        raise RuntimeError("Groq client/API key not available. Set GROQ_API_KEY in app secrets.")
    return Groq(api_key=api_key)

def call_groq_analyze(text: str, model: str) -> Dict[str, Any]:
    client = _groq_client()
    prompt = (PROMPT_ANALYZE_NL if NL else PROMPT_ANALYZE_EN) + text
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You must output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1600,
        response_format={"type": "json_object"},
    )
    return json.loads(completion.choices[0].message.content)

def call_groq_compare(text_a: str, text_b: str, model: str) -> Dict[str, Any]:
    client = _groq_client()
    prompt = (PROMPT_COMPARE_NL if NL else PROMPT_COMPARE_EN) + "\n\nTEXT A (old/oud):\n" + text_a + "\n\nTEXT B (new/nieuw):\n" + text_b
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You must output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=2400,
        response_format={"type": "json_object"},
    )
    return json.loads(completion.choices[0].message.content)

# ---------- UI Tabs ----------
TAB_ONE, TAB_TWO = st.tabs([T("Contract Analysis", "Contract Analysis"), T("Contract Vergelijk", "Compare Contracts")])

with TAB_ONE:
    uploaded = st.file_uploader(T("Upload contract (PDF/DOCX/TXT)", "Upload contract (PDF/DOCX/TXT)"), type=["pdf","docx","txt"], key="single")

    if uploaded:
        text = read_file_to_text(uploaded)
        st.subheader("📑 " + T("Voorbeeld", "Preview"))
        st.text_area(T("Eerste ~3000 tekens", "First ~3000 chars"), text[:3000], height=180)

        if st.button(T("Analyseren", "Analyze"), type="primary"):
            with st.spinner(T("Analyseren met Groq...", "Analyzing with Groq...")):
                try:
                    data = call_groq_analyze(text[:8000], model_name)
                except Exception as e:
                    st.error((T("Analyse mislukt: ", "Analysis failed: ") + str(e)))
                    data = None

            if data:
                st.success(T("Analyse gereed", "Analysis complete"))
                st.subheader(T("Belangrijkste clausules", "Key clauses"))
                for c in data.get("key_clauses", []) or []:
                    st.write(f"- {c}")
                st.subheader("Risks")
                for r in data.get("risks", []) or []:
                    st.write(f"- {r}")
                st.subheader(T("Aanbevelingen", "Recommendations"))
                for rec in data.get("recommendations", []) or []:
                    st.write(f"- {rec}")
    else:
        st.info(T("Upload een document om te starten.", "Upload a document to get started."))

with TAB_TWO:
    st.subheader(T("Vergelijk twee contracten", "Compare two contracts"))
    colA, colB = st.columns(2)
    with colA:
        up_a = st.file_uploader(T("Oud contract (PDF/DOCX/TXT)", "Old contract (PDF/DOCX/TXT)"), type=["pdf","docx","txt"], key="old")
    with colB:
        up_b = st.file_uploader(T("Nieuw contract (PDF/DOCX/TXT)", "New contract (PDF/DOCX/TXT)"), type=["pdf","docx","txt"], key="new")

    if up_a and up_b:
        text_a = read_file_to_text(up_a)
        text_b = read_file_to_text(up_b)

        with st.expander(T("Voorbeeld A (oud)", "Preview A (old)"), expanded=False):
            st.text_area("A", text_a[:2000], height=150)
        with st.expander(T("Voorbeeld B (nieuw)", "Preview B (new)"), expanded=False):
            st.text_area("B", text_b[:2000], height=150)

        if st.button(T("Vergelijk", "Compare"), type="primary"):
            with st.spinner(T("Vergelijking bezig...", "Running comparison...")):
                try:
                    comp_llm = call_groq_compare(text_a[:10000], text_b[:10000], model_name)
                except Exception as e:
                    st.error((T("Vergelijking mislukt: ", "Comparison failed: ") + str(e)))
                    comp_llm = None

            if comp_llm:
                st.success(T("Resultaat gereed", "Result ready"))

                st.markdown("###   Grote wijzigingen")
                for ch in comp_llm.get("major_changes", [])[:50]:
                    tag = f"[{ch.get('type','')}/{ch.get('change','')}]".strip("[]/")
                    title = ch.get("title", "")
                    note = ch.get("note", "")
                    before = ch.get("before")
                    after = ch.get("after")
                    impact = ch.get("impact")
                    line = f"- {tag} {title}: {note}" if note else f"- {tag} {title}"
                    st.write(line)
                    if before or after or impact:
                        with st.expander(T("Details", "Details"), expanded=False):
                            if impact:
                                st.write(f"• Impact: {impact}")
                            if before:
                                st.write(f"• Before: {before}")
                            if after:
                                st.write(f"• After: {after}")

                st.markdown("### " + T("Eindoordeel", "Overall assessment"))
                st.write(comp_llm.get("overall_assessment", ""))
                st.markdown("**" + T("Onderhandelen?", "Should renegotiate?") + "** " + str(comp_llm.get("should_renegotiate", False)))

                if comp_llm.get("key_points_to_verify"):
                    st.markdown("### " + T("Belangrijke controlepunten", "Key points to verify"))
                    for k in comp_llm.get("key_points_to_verify", [])[:20]:
                        st.write(f"- {k}")

                # Pricing comparison (optional)
                pc = comp_llm.get("pricing_compare") or {}
                if pc:
                    st.markdown("### " + T("Prijsvergelijking", "Pricing comparison"))
                    totals = pc.get("totals") or {}
                    cur = totals.get("currency") or ""
                    for k in ["one_time", "monthly", "yearly"]:
                        row = totals.get(k)
                        if isinstance(row, dict):
                            st.write(f"- {k}: {cur} {row.get('old')} → {cur} {row.get('new')} (Δ {row.get('delta')})")
                    if pc.get("items_added"):
                        st.markdown("**" + T("Items toegevoegd", "Items added") + ":**")
                        for it in pc.get("items_added", [])[:20]:
                            desc = it.get("description", "")
                            qty = it.get("qty"); unit = it.get("unit") or ""
                            uprice = it.get("unit_price"); curr = it.get("currency") or cur
                            period = it.get("period") or ""; total = it.get("line_total")
                            bits = []
                            if qty is not None: bits.append(str(qty))
                            if unit: bits.append(unit)
                            qty_unit = " ".join(bits)
                            st.write(
                                f"- {desc} — {qty_unit} @ {curr} {uprice} {('/' + period) if period else ''}" +
                                (f" ⇒ {curr} {total}" if total is not None else "")
                            )
                    if pc.get("items_removed"):
                        st.markdown("**" + T("Items verwijderd", "Items removed") + ":**")
                        for it in pc.get("items_removed", [])[:20]:
                            st.write(f"- {it.get('description','')}")
                    if pc.get("items_modified"):
                        st.markdown("**" + T("Items gewijzigd", "Items modified") + ":**")
                        for it in pc.get("items_modified", [])[:20]:
                            st.write(f"- {it.get('description','')}")
                            for f, d in (it.get('fields_changed') or it.get('diff') or {}).items():
                                st.write(f"  - {f}: {d.get('old')} → {d.get('new')}")
                    if pc.get("price_changes"):
                        st.markdown("**" + T("Prijswijzigingen", "Price change rules") + ":**")
                        for ch in pc.get("price_changes", {}).get("new", [])[:20]:
                            t = ch.get("type","change"); amt = ch.get("amount"); pct = ch.get("percent")
                            eff = ch.get("effective_date") or ""; note = ch.get("note") or ""
                            parts = [t]
                            if pct is not None: parts.append(f"{pct}%")
                            if amt is not None: parts.append(f"{cur} {amt}")
                            if eff: parts.append(f"effective {eff}")
                            if note: parts.append(f"— {note}")
                            st.write("- " + ", ".join(parts))
                        if pc.get("price_changes", {}).get("diff_summary"):
                            st.write("- " + str(pc["price_changes"]["diff_summary"]))
                    if pc.get("indexation"):
                        idx = pc.get("indexation", {})
                        old_i = idx.get("old") or {}
                        new_i = idx.get("new") or {}
                        if old_i or new_i:
                            st.write("- " + T("Indexatie oud", "Indexation old") + ": " + ", ".join(f"{k}={v}" for k,v in old_i.items() if v not in (None, "")))
                            st.write("- " + T("Indexatie nieuw", "Indexation new") + ": " + ", ".join(f"{k}={v}" for k,v in new_i.items() if v not in (None, "")))

                # Downloads
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        T("Download JSON", "Download JSON"),
                        data=json.dumps(comp_llm, ensure_ascii=False, indent=2).encode("utf-8"),
                        file_name="shpr_ai_major_changes.json",
                        mime="application/json",
                    )
                with col2:
                    md_lines: List[str] = ["# Major Changes\n"]
                    for ch in comp_llm.get("major_changes", [])[:50]:
                        tag = f"[{ch.get('type','')}/{ch.get('change','')}]".strip("[]/")
                        title = ch.get("title", "")
                        note = ch.get("note", "")
                        md_lines.append(f"- {tag} {title}: {note}")
                    # Optional pricing summary in Markdown
                    pc = comp_llm.get("pricing_compare") or {}
                    if pc:
                        md_lines.append("\n## " + T("Prijsvergelijking", "Pricing comparison"))
                        totals = pc.get("totals") or {}
                        cur = totals.get("currency") or ""
                        for k in ["one_time", "monthly", "yearly"]:
                            row = totals.get(k)
                            if isinstance(row, dict):
                                md_lines.append(f"- {k}: {cur} {row.get('old')} → {cur} {row.get('new')} (Δ {row.get('delta')})")
                        if pc.get("price_changes", {}).get("diff_summary"):
                            md_lines.append("- " + str(pc["price_changes"]["diff_summary"]))

                    md_lines.append("\n## " + T("Eindoordeel", "Overall assessment"))
                    md_lines.append(comp_llm.get("overall_assessment", ""))
                    md_lines.append("\n**" + T("Onderhandelen?", "Should renegotiate?") + "** " + str(comp_llm.get("should_renegotiate", False)))
                    if comp_llm.get("key_points_to_verify"):
                        md_lines.append("\n## " + T("Belangrijke controlepunten", "Key points to verify"))
                        for k in comp_llm.get("key_points_to_verify", [])[:20]:
                            md_lines.append(f"- {k}")
                    st.download_button(
                        T("Download Markdown", "Download Markdown"),
                        data="\n".join(md_lines).encode("utf-8"),
                        file_name="shpr_ai_major_changes.md",
                        mime="text/markdown",
                    )
    else:
        st.info(T("Upload beide documenten om te vergelijken.", "Upload both documents to compare."))

st.markdown("---")
st.caption(T(
    "Beide tabbladen zijn AI only: tab 1 samenvatting, tab 2 Major Changes.",
    "Both tabs are AI only: tab 1 summary, tab 2 Major Changes.",
))
