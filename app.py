"""BookRAG — Streamlit chat UI over the agentic multimodal RAG pipeline.

UX highlights:
  - Live pipeline progress (LangGraph .stream): routing -> retrieving -> generating -> verifying.
  - Source-citation cards with TEXT/TABLE badges, source, page and fusion score.
  - Grounding verdict badge + honest disclaimer when the answer can't be verified.
  - Corpus dashboard sidebar + endpoint health check.
"""
from __future__ import annotations

import json

import streamlit as st

import config

st.set_page_config(page_title="BookRAG — Finance Intelligence", page_icon="📚", layout="wide")

# ------------------------------------------------------------------ styling
st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1100px;}
      .brand {font-size: 1.9rem; font-weight: 800; letter-spacing: -.02em;}
      .brand span {background: linear-gradient(90deg,#6366f1,#22d3ee);
                   -webkit-background-clip: text; -webkit-text-fill-color: transparent;}
      .subtle {color:#8b93a7; font-size:.9rem; margin-top:-.3rem;}
      .badge {display:inline-block; padding:2px 9px; border-radius:999px;
              font-size:.72rem; font-weight:600; margin-right:6px;}
      .b-text {background:#1e293b; color:#93c5fd;}
      .b-table {background:#3b1e2e; color:#fca5a5;}
      .b-ok {background:#052e1a; color:#4ade80;}
      .b-warn {background:#3a2a05; color:#fbbf24;}
      .b-src {background:#1e293b; color:#cbd5e1;}
      .srccard {border:1px solid #26304a; border-radius:10px; padding:10px 12px;
                margin-bottom:8px; background:#0f1526;}
      .srccard .t {font-weight:600; font-size:.9rem;}
      .srccard .m {color:#8b93a7; font-size:.78rem; margin-top:2px;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ startup guard
if not (config.CHROMA_DIR / "bm25.pkl").exists():
    st.error("🗄️ Vector database not found. Run `python ingest.py` first, then restart the app.")
    st.stop()


# ------------------------------------------------------------------ cached resources
@st.cache_resource(show_spinner="Loading pipeline & models…")
def load_pipeline():
    from pipeline import build_graph
    return build_graph()


@st.cache_resource(show_spinner=False)
def load_router_llm():
    from utils.llm import make_llm
    return make_llm(config.MODEL_ROUTER, temperature=0.0)


def endpoint_ok() -> bool:
    try:
        import requests
        requests.get(config.LLM_BASE_URL.rstrip("/") + "/v1/models", timeout=3)
        return True
    except Exception:
        try:
            import requests
            requests.get(config.LLM_BASE_URL, timeout=3)
            return True
        except Exception:
            return False


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### 📊 Corpus")
    if config.INGEST_STATE.exists():
        state = json.loads(config.INGEST_STATE.read_text())
        c1, c2 = st.columns(2)
        c1.metric("Documents", state.get("documents", "—"))
        c2.metric("Chunks", f"{state.get('chunks', 0):,}")
        c1.metric("Tables", f"{state.get('table_chunks', 0):,}")
        c2.metric("Sources", len(state.get("by_source", {})))
        with st.expander("By source"):
            for s, n in sorted(state.get("by_source", {}).items(), key=lambda x: -x[1]):
                st.write(f"`{s}` — {n:,} chunks")
    else:
        st.info("Run `python ingest.py` to build the index.")

    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    show_trace = st.toggle("Show pipeline trace", value=True)
    st.caption(f"LLM endpoint: `{config.LLM_BASE_URL}`")
    st.caption("🟢 reachable" if endpoint_ok() else "🔴 unreachable — set OLLAMA_BASE_URL in .env")
    if st.button("🧹 Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.pop("history", None)
        st.rerun()

# ------------------------------------------------------------------ header
st.markdown('<div class="brand">📚 Book<span>RAG</span></div>', unsafe_allow_html=True)
st.markdown('<div class="subtle">Agentic, grounded Q&A over a multimodal finance & wealth corpus.</div>',
            unsafe_allow_html=True)
st.write("")

# ------------------------------------------------------------------ state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "history" not in st.session_state:
    from utils.history import ChatHistory
    st.session_state.history = ChatHistory(load_router_llm())

pipeline_app = load_pipeline()

NODE_STATUS = {
    "rewrite_and_route": "🧭 Understanding & routing the question…",
    "retrieve": "🔎 Retrieving from Chroma + BM25 (RRF fusion)…",
    "generate": "✍️ Generating a grounded answer…",
    "evaluate_grounding": "🛡️ Verifying every claim against sources…",
    "expand_query": "♻️ Expanding query & retrying for better grounding…",
    "general_answer": "💬 Answering…",
    "build_final_answer": "📦 Finalising…",
}


def _badge(kind: str) -> str:
    return ('<span class="badge b-table">TABLE</span>' if kind == "table"
            else '<span class="badge b-text">TEXT</span>')


def render_sources(sources: list[dict]) -> None:
    seen = set()
    for s in sources:
        key = (s.get("title"), s.get("page"), s.get("element_type"))
        if key in seen:
            continue
        seen.add(key)
        page = f" · p.{s['page']}" if s.get("page") else ""
        st.markdown(
            f'<div class="srccard">{_badge(s.get("element_type","text"))}'
            f'<span class="t">{s.get("title","document")}</span>'
            f'<div class="m"><span class="badge b-src">{s.get("source","")}</span>{page}'
            f' · fusion {s.get("rrf_score",0)}</div></div>',
            unsafe_allow_html=True,
        )


def render_trace(trace: dict) -> None:
    with st.expander("🧩 Pipeline trace", expanded=False):
        route = trace.get("route", "rag")
        st.markdown(
            ('<span class="badge b-src">💬 General</span>' if route == "general"
             else '<span class="badge b-src">📚 Knowledge Base</span>'),
            unsafe_allow_html=True,
        )
        if trace.get("rewritten_query") and trace["rewritten_query"] != trace.get("raw_query"):
            st.caption(f"**Rewritten:** {trace['rewritten_query']}")
        if route == "rag":
            grounded = trace.get("is_grounded")
            st.markdown(
                (f'<span class="badge b-ok">✓ Verified</span>' if grounded
                 else f'<span class="badge b-warn">⚠ Unverified</span>')
                + f' <span class="subtle">{trace.get("grounding_reason","")}</span>',
                unsafe_allow_html=True,
            )
            if trace.get("retry_count", 0) >= 1:
                st.caption("🔁 Query was expanded and retried once.")


# ------------------------------------------------------------------ render history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="📚" if msg["role"] == "assistant" else None):
        st.markdown(msg["content"])
        if msg.get("disclaimer"):
            st.warning(msg["disclaimer"])
        if msg["role"] == "assistant" and msg.get("sources"):
            with st.expander(f"📎 {len({(s['title'],s['page']) for s in msg['sources']})} sources"):
                render_sources(msg["sources"])
        if msg["role"] == "assistant" and show_trace and msg.get("trace"):
            render_trace(msg["trace"])


# ------------------------------------------------------------------ chat input
if prompt := st.chat_input("Ask about markets, filings, wealth-building, a company…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    history = st.session_state.history
    history.add_turn("user", prompt)
    init_state = {"raw_query": prompt, "chat_context": history.get_context_messages()}

    with st.chat_message("assistant", avatar="📚"):
        status = st.status("Starting…", expanded=True)
        final: dict = {}
        try:
            for update in pipeline_app.stream(init_state, stream_mode="updates"):
                for node, delta in update.items():
                    status.update(label=NODE_STATUS.get(node, node))
                    if isinstance(delta, dict):
                        final.update(delta)
            status.update(label="Done", state="complete", expanded=False)
        except Exception as e:  # noqa: BLE001
            status.update(label="LLM call failed", state="error")
            st.error(
                f"Could not reach the LLM endpoint (`{config.LLM_BASE_URL}`).\n\n"
                f"Set `OLLAMA_BASE_URL` in `.env` to a running OpenAI-compatible server "
                f"and reload.\n\n_Details: {e}_"
            )
            st.stop()

        answer = final.get("final_answer") or final.get("generated_answer") or "_No answer produced._"
        st.markdown(answer)
        disclaimer = final.get("disclaimer", "")
        if disclaimer:
            st.warning(disclaimer)
        sources = final.get("sources", [])
        trace = {
            "route": final.get("route", "rag"),
            "raw_query": prompt,
            "rewritten_query": final.get("rewritten_query", ""),
            "retry_count": final.get("retry_count", 0),
            "is_grounded": final.get("is_grounded"),
            "grounding_reason": final.get("grounding_reason", ""),
        }
        if sources:
            with st.expander(f"📎 {len({(s['title'], s['page']) for s in sources})} sources"):
                render_sources(sources)
        if show_trace:
            render_trace(trace)

    history.add_turn("assistant", answer)
    st.session_state.messages.append({
        "role": "assistant", "content": answer, "sources": sources,
        "disclaimer": disclaimer, "trace": trace,
    })
