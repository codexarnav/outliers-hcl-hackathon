"""
Streamlit User Interface
AI-Powered University Student Services Assistant
Delhi Technological University (DTU)
"""

import os
import json
import requests
import streamlit as st
from datetime import datetime

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="DTU Student Services Assistant",
    page_icon="🎓",
    layout="wide"
)

# Header
st.title("🎓 DTU Academic Services Assistant")
st.caption("Deterministic, Grounded AI Assistant for Delhi Technological University (`dtu.ac.in`)")

# Sidebar
with st.sidebar:
    st.header("🔐 Student Authentication (R7)")
    student_preset = st.selectbox(
        "Select Active Student Profile:",
        [
            "Anonymous (General Inquirer)",
            "S1001 — Aarav Sharma (CO201 Attendance: 75.0% - Exact Threshold)",
            "S1002 — Diya Patel (CO201 Attendance: 72.5% - 1 Class Below)",
            "S1003 — Rohan Verma (CO201 Attendance: 65.0% - Condonation Case)",
            "S1004 — Ananya Iyer (CO201 Result: FAIL - 39% Marks)",
            "S1006 — Meera Nair (Active Backlogs: 4 - Promotion Edge Case)",
            "S1007 — Aditya Joshi (CO201 Attendance: 50.0% - DETAINED)",
            "Custom Student ID"
        ]
    )

    if student_preset == "Anonymous (General Inquirer)":
        student_id = None
    elif student_preset == "Custom Student ID":
        student_id = st.text_input("Enter Student ID (e.g. S1001):").strip() or None
    else:
        student_id = student_preset.split(" — ")[0]

    st.markdown("---")
    st.header("📅 Evaluation Date Context (R4)")
    as_of_date = st.date_input(
        "As-of Date:",
        value=datetime.now().date(),
        help="Test time-travel conflict resolution: e.g. before/after 2026-08-01 amendment"
    ).strftime("%Y-%m-%d")

    st.markdown("---")
    st.header("🏥 System Health Status")
    try:
        health_resp = requests.get(f"{API_BASE_URL}/health", timeout=2)
        if health_resp.status_code == 200:
            h = health_resp.json()
            st.success(f"API: {h['api']} | SQLite: {h['sqlite']} | Chroma: {h['vector_store']}")
            st.info(f"Mode: {'MOCK_LLM (Deterministic)' if h.get('mock_mode') else 'Local Ollama'}")
        else:
            st.warning("API degraded")
    except Exception:
        st.error("API disconnected. Ensure `uvicorn main:app` is running.")

    st.markdown("---")
    st.header("📄 Live Document Ingestion (R11)")
    with st.expander("Upload New University Document"):
        uploaded_file = st.file_uploader("Document File (PDF / TXT):", type=["pdf", "txt"])
        ingest_doc_id = st.text_input("Document ID (e.g. DTU-NOTIF-LIVE-01):", value="DTU-NOTIF-LIVE-01")
        ingest_title = st.text_input("Title:", value="Office Order: Summer Internship Attendance Credit")
        ingest_auth = st.selectbox("Authority Level (Annex A):", [1, 2, 3, 4, 5], index=1)
        ingest_date = st.date_input("Effective From:", value=datetime.now().date()).strftime("%Y-%m-%d")

        if st.button("Ingest Document Live", use_container_width=True):
            if uploaded_file and ingest_doc_id:
                meta = {
                    "doc_id": ingest_doc_id,
                    "title": ingest_title,
                    "issuer": "Office of the Dean Academic",
                    "authority_level": ingest_auth,
                    "doc_type": "circular",
                    "version": "1.0",
                    "effective_from": ingest_date,
                    "effective_to": "",
                    "supersedes": "",
                    "scope_programmes": "ALL",
                    "scope_batches": "ALL",
                    "provenance": "UI Upload",
                    "synthetic": "Y"
                }
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                data = {"metadata": json.dumps(meta)}
                try:
                    ing_res = requests.post(f"{API_BASE_URL}/ingest", files=files, data=data, timeout=10)
                    if ing_res.status_code == 200:
                        st.success(f"Indexed {ing_res.json().get('chunks_indexed', 0)} chunks into ChromaDB & SQLite FTS5!")
                    else:
                        st.error(f"Ingest failed: {ing_res.text}")
                except Exception as e:
                    st.error(f"Error connecting to API: {e}")

# Quick Question Buttons
st.markdown("### 💡 Sample Evaluation Scenarios")
col1, col2, col3, col4 = st.columns(4)
q_text = ""

with col1:
    if st.button("Policy: Minimum Attendance Rule", use_container_width=True):
        q_text = "What is the minimum attendance required to appear for end-semester examinations?"

with col2:
    if st.button("Personal: My CO201 Attendance", use_container_width=True):
        q_text = "What is my attendance in Data Structures (CO201)?"

with col3:
    if st.button("What-If: Supplementary & Placement", use_container_width=True):
        q_text = "I failed CO201. If I pass the supplementary exam, will I be eligible for campus placement?"

with col4:
    if st.button("Abstention: Antarctica Scholarship", use_container_width=True):
        q_text = "What is the scholarship amount for studying in Antarctica?"

# Query Input
user_question = st.text_input("Ask any question regarding DTU academic regulations or your records:", value=q_text)

if st.button("Ask Assistant", type="primary", use_container_width=True) or user_question:
    if not user_question.strip():
        st.warning("Please enter a question.")
    else:
        headers = {}
        if student_id:
            headers["X-Student-Id"] = student_id

        payload = {
            "question": user_question.strip(),
            "as_of_date": as_of_date
        }

        with st.spinner("Retrieving regulations, verifying precedence, and executing deterministic tools..."):
            try:
                resp = requests.post(f"{API_BASE_URL}/ask", json=payload, headers=headers, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()

                    # Answer Type Badge
                    type_colors = {
                        "retrieved_fact": "green",
                        "calculated": "blue",
                        "refused": "red",
                        "not_found": "gray",
                        "conflict_flagged": "orange",
                        "clarification_needed": "violet"
                    }
                    badge_color = type_colors.get(data.get("answer_type", "not_found"), "gray")
                    
                    st.markdown(f"**Answer Type:** :{badge_color}[`{data.get('answer_type', '').upper()}`] | **Trace ID:** `{data.get('trace_id')}`")
                    
                    # Main Answer Callout
                    st.info(data.get("answer", ""))

                    # Tabs for Details
                    tab_cit, tab_tools, tab_rules, tab_audit = st.tabs(["📚 Citations (R2)", "⚙️ Deterministic Tools (R5)", "⚖️ Applied Rules", "🔍 Full Audit Record (R10)"])

                    with tab_cit:
                        citations = data.get("citations", [])
                        if citations:
                            for c in citations:
                                st.markdown(f"**Document:** `{c.get('doc_id')}` — *{c.get('title')}*")
                                st.markdown(f"*Section/Clause:* `{c.get('section')}` | *Page:* {c.get('page')} | *Version:* {c.get('version')} | *Effective:* {c.get('effective_from')}")
                                st.markdown("---")
                        else:
                            st.write("No document citations required for this response type.")

                    with tab_tools:
                        tools = data.get("tools_invoked", [])
                        if tools:
                            for t in tools:
                                st.markdown(f"**Tool:** `{t.get('tool')}`")
                                st.json({"input": t.get("input"), "output": t.get("output")})
                        else:
                            st.write("No deterministic tools were invoked for this query.")

                    with tab_rules:
                        rules = data.get("applied_rules", [])
                        if rules:
                            for r in rules:
                                st.markdown(f"• **Rule:** `{r.get('rule_id')}` | **Threshold:** `{r.get('value')}` | **Source:** `{r.get('source_doc_id')}`")
                        else:
                            st.write("No specific registry rules applied.")

                    with tab_audit:
                        try:
                            audit_resp = requests.get(f"{API_BASE_URL}/audit/{data.get('trace_id')}", timeout=3)
                            if audit_resp.status_code == 200:
                                st.json(audit_resp.json())
                            else:
                                st.write("Audit record details in response:", data)
                        except Exception:
                            st.write("Audit trace:", data)

                else:
                    st.error(f"Error {resp.status_code}: {resp.text}")
            except Exception as e:
                st.error(f"Failed to communicate with API server: {e}")
