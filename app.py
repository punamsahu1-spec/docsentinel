"""
DocSentinel — app.py
Explorer | Detect Stale Docs | Repair Engine
"""

import json
import streamlit as st
from engine import index_repo, detect_changes, apply_repairs
from config import MAP_OUTPUT

st.set_page_config(page_title="DocSentinel", page_icon="🛡️", layout="wide")
st.title("🛡️ DocSentinel — Self-Healing Documentation")

mode = st.sidebar.radio("Mode", [
    "🗂️ Explorer",
    "🔍 Detect Stale Docs",
    "🔧 Repair Engine",
])

# ── Explorer ───────────────────────────────────────────────────────────────────
if mode == "🗂️ Explorer":
    repo_path = st.sidebar.text_input("Repo path", value="./demo_repo")

    if st.sidebar.button("🔍 Index Repo", use_container_width=True):
        with st.spinner("Indexing..."):
            graph = index_repo(repo_path)
        st.session_state["graph"] = graph

    if "graph" in st.session_state:
        g = st.session_state["graph"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Code Chunks", len(g["code_chunks"]))
        c2.metric("Doc Sections", len(g["doc_sections"]))
        c3.metric("Links", len(g["links"]))

        st.subheader("Code → Doc Link Graph")
        for link in g["links"]:
            badge = "🔤 name match" if link["method"] == "name_match" else f"🧠 embedding ({link['score']:.2f})"
            st.markdown(f"- `{link['code_id']}` → `{link['doc_id']}` {badge}")

        with st.expander("Raw map JSON"):
            st.json(g)
    else:
        st.info("Enter repo path and click **Index Repo**.")

# ── Detect ─────────────────────────────────────────────────────────────────────
elif mode == "🔍 Detect Stale Docs":
    st.subheader("Detect Stale Documentation from Code Changes")

    repo_path = st.text_input("Repo path", value="./demo_repo")
    base_branch = st.text_input("Base branch", value="main")

    if st.button("🔍 Detect Stale Sections", use_container_width=True):
        with st.spinner("git diff → link graph → LLM verification..."):
            try:
                stale = detect_changes(repo_path, MAP_OUTPUT, base_branch)
                st.session_state["stale"] = stale
            except Exception as e:
                st.error(f"Error: {e}")

    if "stale" in st.session_state:
        stale = st.session_state["stale"]
        if not stale:
            st.success("✅ No stale documentation detected.")
        else:
            st.warning(f"⚠️ {len(stale)} stale section(s) found — go to **Repair Engine** to fix")
            for s in stale:
                with st.expander(f"📄 {s['doc_section']['heading']}", expanded=True):
                    c1, c2 = st.columns(2)
                    c1.metric("Confidence", f"{s['confidence']:.0%}")
                    c2.markdown(f"**Reason:** {s['reason']}")
                    st.markdown("**Stale section:**")
                    st.code(s["doc_section"]["full_text"], language="markdown")
                    st.markdown("**Code diff:**")
                    st.code(s["diff"][:1500], language="diff")

# ── Repair ─────────────────────────────────────────────────────────────────────
elif mode == "🔧 Repair Engine":
    st.subheader("Repair Stale Documentation")

    repo_path = st.text_input("Repo path", value="./demo_repo")

    if "stale" not in st.session_state:
        st.warning("Run **Detect Stale Docs** first.")
    else:
        stale = st.session_state["stale"]
        st.info(f"{len(stale)} stale section(s) queued for repair.")

        if st.button("🔧 Repair All", use_container_width=True):
            with st.spinner("Repairing → validating → applying fixes..."):
                results = apply_repairs(stale, repo_path)
                st.session_state["results"] = results

        if "results" in st.session_state:
            results = st.session_state["results"]

            auto_fixed = [r for r in results if r["mode"] == "auto_fix" and r.get("applied")]
            review = [r for r in results if r["mode"] == "human_review"]
            skipped = [r for r in results if r["mode"] == "skip"]

            c1, c2, c3 = st.columns(3)
            c1.metric("✅ Auto-Fixed", len(auto_fixed))
            c2.metric("🟡 Needs Review", len(review))
            c3.metric("⏭️ Skipped", len(skipped))

            for r in results:
                icon = "✅" if r.get("applied") else ("🟡" if r["mode"] == "human_review" else "⏭️")
                with st.expander(f"{icon} {r['doc_section']['heading']} — {r['mode']}", expanded=True):
                    st.markdown(f"**Repair confidence:** {r['repair_confidence']:.0%}")
                    st.markdown(f"**Changes made:** {r['changes_made']}")
                    st.markdown(f"**Validation:** {r.get('validation_note', 'N/A')}")

                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Original:**")
                        st.code(r["doc_section"]["full_text"], language="markdown")
                    with c2:
                        st.markdown("**Repaired:**")
                        st.code(r.get("repaired_text", ""), language="markdown")
