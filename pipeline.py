"""LangGraph agentic RAG pipeline.

START -> rewrite_and_route
  general -> general_answer -> build_final_answer -> END
  rag     -> retrieve -> generate -> evaluate_grounding
                 grounded or retried -> build_final_answer -> END
                 ungrounded (1st try) -> expand_query -> retrieve (loop)

Enhancements over the base spec: excerpts are labelled TEXT vs TABLE with source +
page so the model can cite precisely and reason over financial tables.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import StateGraph, START, END

import json

import config
from utils.llm import make_llm, invoke_text, parse_json
from utils.retrieval import get_retriever
from utils.tools import TOOL_MENU, execute_tool
from utils.websearch import web_search


class RAGState(TypedDict, total=False):
    raw_query: str
    rewritten_query: str
    route: str
    retrieved_docs: list
    first_attempt_docs: list
    generated_answer: str
    is_grounded: bool
    grounding_reason: str
    retry_count: int
    expanded_query: str
    final_answer: str
    disclaimer: str
    sources: list
    chat_context: list
    tool_calls: list
    search_results: list
    project_id: str
    cross_reference: dict


DISCLAIMER = (
    "⚠️ Note: I could not fully verify this answer against the source "
    "documents after two attempts. Some claims may not be directly grounded in the "
    "texts. Please treat this response with caution and consider cross-referencing "
    "the originals. Feel free to rephrase your question for a more targeted search."
)


def _format_docs(docs: list[dict], cap: int | None = None) -> str:
    """Render excerpts for a prompt. `cap` trims each excerpt — the grounding evaluator
    passes a smaller cap because it only needs to trace claims, not read full passages.
    Token budget matters: Groq's free tier is ~6k tokens/MINUTE, and excerpts would
    otherwise be sent twice per turn (generate + evaluate)."""
    cap = cap or config.EXCERPT_CHARS
    blocks = []
    for d in docs:
        kind = "TABLE" if d.get("element_type") == "table" else "TEXT"
        page = f", p.{d['page']}" if d.get("page") else ""
        text = d["text"]
        if len(text) > cap:
            text = text[:cap] + " …"
        blocks.append(f"[{kind}] Source: {d.get('title', 'document')} ({d.get('source', '')}{page})\n{text}\n---")
    return "\n".join(blocks)


def build_graph():
    """Compile and return the LangGraph app. LLM clients are created once here."""
    router = make_llm(config.MODEL_ROUTER, temperature=0.0)
    general_llm = make_llm(config.MODEL_GENERAL, temperature=0.5)
    gen = make_llm(config.MODEL_HEAVY, temperature=0.35)   # natural, human generation
    heavy = make_llm(config.MODEL_HEAVY, temperature=0.1)  # strict, deterministic evaluation
    retriever = get_retriever()

    # ---------------------------------------------------------------- nodes
    def rewrite_and_route(state: RAGState) -> RAGState:
        raw = state["raw_query"]
        system = "You are a query processor. Respond ONLY with valid JSON, no explanation, no markdown fences."
        user = (
            "Given the user query below, do two things:\n"
            "1. Rewrite it to be clearer and more search-friendly. Keep the meaning identical.\n"
            "2. Classify the route into exactly one of:\n"
            "   - \"tool\"    : needs live/computed data — weather, a stock or crypto price, a "
            "currency conversion, a math calculation, or the current time.\n"
            "   - \"search\"  : needs current, real-world or recent web info NOT in a finance "
            "document library — latest news, recent events, today's headlines, a current fact.\n"
            "   - \"rag\"     : answerable from a finance/business/wealth document corpus "
            "(companies, filings, markets, investing concepts).\n"
            "   - \"general\" : conversational (hi, thanks, who made you, what can you do).\n"
            'Respond ONLY with: {"rewritten_query": "...", "route": "tool|search|rag|general"}\n\n'
            f"User query: {raw}"
        )
        data = parse_json(invoke_text(router, [
            {"role": "system", "content": system}, {"role": "user", "content": user},
        ]), default={})
        route = data.get("route", "rag")
        if route not in ("tool", "search", "rag", "general"):
            route = "rag"
        return {
            "rewritten_query": data.get("rewritten_query", raw) or raw,
            "route": route,
            "retry_count": 0,
        }

    def _retrieve_all(query: str, extra_docs=None, project_id: str = "") -> list:
        """Base-corpus retrieval, plus the chat's project documents (prioritised)."""
        base = retriever.retrieve(query, extra_docs=extra_docs)
        if not project_id:
            return base
        try:
            from server.project_store import retrieve as proj_ret
            proj = proj_ret(project_id, query, n=6)
        except Exception:
            proj = []
        if not proj:
            return base
        seen, merged = set(), []
        for d in proj + base:                     # the user's uploaded docs come first
            k = d["text"][:80]
            if k in seen:
                continue
            seen.add(k)
            merged.append(d)
            if len(merged) >= config.N_FINAL:
                break
        return merged

    def retrieve(state: RAGState) -> RAGState:
        pid = state.get("project_id", "")
        if state.get("retry_count", 0) == 0:
            docs = _retrieve_all(state["rewritten_query"], project_id=pid)
            return {"retrieved_docs": docs, "first_attempt_docs": docs}
        docs = _retrieve_all(state["expanded_query"],
                             extra_docs=state.get("first_attempt_docs"), project_id=pid)
        return {"retrieved_docs": docs}

    def generate(state: RAGState) -> RAGState:
        docs = state["retrieved_docs"]
        system = (
            "You are BookRAG — a sharp, personable finance & business analyst. Answer the user's "
            "question grounded ONLY in the provided source excerpts (some are Markdown TABLES — read "
            "the figures carefully). Sound like a knowledgeable person talking to a colleague, not like "
            "a report or a Wikipedia entry.\n\n"
            "STYLE — this matters a lot:\n"
            "• Match length and depth to the question. A simple/factual question gets a crisp 1–3 "
            "sentence answer; a broad one gets more. Never pad or over-explain.\n"
            "• Default to natural flowing prose. Use bullet points ONLY when genuinely enumerating 3+ "
            "parallel items — never as your default format.\n"
            "• Weave sources in naturally (e.g. \"NVIDIA's 10-K flags…\") instead of stiff citations "
            "after every sentence.\n"
            "• Build on the conversation so far — refer back to what was already discussed, and adapt to "
            "the user's apparent level and interests. Be direct, warm, and human.\n"
            "• If the excerpts genuinely don't cover the question, say so briefly in one line and suggest "
            "what would help — do not guess or invent."
        )
        user = (
            f"User's question: {state['raw_query']}\n\n"
            f"Source excerpts to ground your answer:\n{_format_docs(docs)}\n\n"
            "Now answer the user naturally, grounded strictly in these excerpts."
        )
        messages = [{"role": "system", "content": system}]
        messages.extend(state.get("chat_context", []))
        messages.append({"role": "user", "content": user})
        return {"generated_answer": invoke_text(gen, messages)}

    def evaluate_grounding(state: RAGState) -> RAGState:
        system = (
            "You are a strict fact-checker. Verify that every factual claim in the answer is "
            "directly supported by the provided source excerpts. Respond ONLY with valid JSON, "
            "no explanation, no markdown fences."
        )
        user = (
            f"Answer to evaluate:\n{state['generated_answer']}\n\n"
            f"Source excerpts used:\n{_format_docs(state['retrieved_docs'], cap=300)}\n\n"
            "Instructions:\n- Check each factual claim against the excerpts.\n"
            "- If ANY claim cannot be traced to an excerpt, mark is_grounded false.\n"
            "- Conversational filler does not count as a claim.\n- Be strict.\n"
            'Respond ONLY with: {"is_grounded": true or false, "reason": "one sentence"}'
        )
        data = parse_json(invoke_text(heavy, [
            {"role": "system", "content": system}, {"role": "user", "content": user},
        ]), default={"is_grounded": False, "reason": "Could not parse evaluator output."})
        return {
            "is_grounded": bool(data.get("is_grounded", False)),
            "grounding_reason": data.get("reason", ""),
        }

    def cross_reference(state: RAGState) -> RAGState:
        """Do the retrieved sources actually agree with each other? Flags contradictions."""
        docs = state.get("retrieved_docs", [])
        if not config.CROSS_REFERENCE:
            return {"cross_reference": {}}
        titles = list(dict.fromkeys([d.get("title", "") for d in docs if d.get("title")]))
        if len(titles) < 2:
            return {"cross_reference": {
                "consensus": "single", "sources_checked": len(titles),
                "agreements": [], "conflicts": [],
                "note": "Only one source document backed this answer — nothing to cross-check."}}

        # Keep this prompt LEAN — it runs on every grounded RAG turn, so a fat prompt here
        # (full excerpts) measurably slowed the whole pipeline. Short snippets are enough
        # to spot agreement/contradiction.
        brief = "\n".join(
            f"[{i+1}] {d.get('title', 'doc')}: {' '.join(d['text'].split())[:220]}"
            for i, d in enumerate(docs[:4]))
        system = ("You verify whether independent sources agree. Respond ONLY with compact valid "
                  "JSON, no explanation, no markdown fences. Keep every string under 20 words.")
        user = (
            f"Answer:\n{state.get('generated_answer', '')[:600]}\n\n"
            f"Sources:\n{brief}\n\n"
            "Compare the sources against the answer's key factual claims.\n"
            "- \"agree\": sources are consistent with each other.\n"
            "- \"partial\": sources cover different aspects but don't contradict.\n"
            "- \"conflict\": at least two sources disagree on a factual claim.\n"
            'Respond ONLY with: {"consensus":"agree|partial|conflict",'
            '"agreements":["short point"],"conflicts":[{"claim":"...","detail":"..."}],'
            '"note":"one sentence"}'
        )
        data = parse_json(invoke_text(router, [
            {"role": "system", "content": system}, {"role": "user", "content": user},
        ]), default={}) or {}
        consensus = data.get("consensus")
        if consensus not in ("agree", "partial", "conflict"):
            consensus = "partial"
        return {"cross_reference": {
            "consensus": consensus,
            "sources_checked": len(titles),
            "agreements": (data.get("agreements") or [])[:4],
            "conflicts": (data.get("conflicts") or [])[:4],
            "note": (data.get("note") or "")[:200],
        }}

    def expand_query(state: RAGState) -> RAGState:
        system = "You are a search query expander. Respond ONLY with the expanded query string, nothing else."
        user = (
            f"The original query: {state['raw_query']}\n"
            f"The rewritten query: {state['rewritten_query']}\n"
            f"Grounding failure reason: {state.get('grounding_reason', '')}\n\n"
            "Generate an expanded version of the rewritten query by adding 4-6 relevant synonyms "
            "or related financial concepts and alternative phrasings, as a single coherent query. "
            "Respond with ONLY the expanded query."
        )
        expanded = invoke_text(router, [
            {"role": "system", "content": system}, {"role": "user", "content": user},
        ])
        return {"expanded_query": expanded or state["rewritten_query"], "retry_count": 1}

    def general_answer(state: RAGState) -> RAGState:
        system = (
            "You are BookRAG — a warm, natural conversational assistant with a finance & business focus. "
            "Reply the way a thoughtful person would in a chat: concise, friendly, and adapted to the "
            "conversation so far. Match your length to the message — a greeting gets a short greeting "
            "back, not a paragraph. Avoid bullet-point dumps; prefer natural sentences. If the user "
            "drifts well outside finance/business/wealth, help them in a sentence or two, then gently "
            "mention you're at your best on finance, markets, companies and wealth topics."
        )
        messages = [{"role": "system", "content": system}]
        messages.extend(state.get("chat_context", []))
        messages.append({"role": "user", "content": state["raw_query"]})
        return {"generated_answer": invoke_text(general_llm, messages)}

    def tool_call(state: RAGState) -> RAGState:
        raw = state["raw_query"]
        # Built-in tools + any tools discovered from connected MCP servers.
        mcp_menu = ""
        try:
            from server import mcp_client
            mcp_menu = mcp_client.menu()
        except Exception:  # noqa: BLE001
            mcp_client = None  # type: ignore

        # 1) pick a tool + args (JSON — portable + mockable)
        sel_system = (
            "You are a tool router. Choose the ONE best tool for the user's request and its "
            "arguments. Respond ONLY with JSON: {\"tool\": \"name\", \"args\": {...}}.\n\nTools:\n"
            + TOOL_MENU + (("\n" + mcp_menu) if mcp_menu else "")
        )
        sel = parse_json(invoke_text(router, [
            {"role": "system", "content": sel_system},
            {"role": "user", "content": raw},
        ]), default={})
        name, args = sel.get("tool", ""), sel.get("args", {}) or {}

        if name.startswith("mcp:"):                       # tool served by an MCP server
            parts = name.split(":", 2)
            if len(parts) == 3:
                from server import mcp_client as _mc
                result = _mc.call_tool(parts[1], parts[2], args)
                via = f"mcp:{parts[1]}"
            else:
                result, via = {"error": f"bad MCP tool name '{name}'"}, "mcp"
        else:
            result = execute_tool(name, args) if name else {"error": "no tool selected"}
            via = "builtin"
        calls = [{"name": name, "args": args, "result": result, "via": via}]

        # 2) synthesize a natural answer from the tool result
        syn_system = (
            "You are BookRAG, a helpful assistant. Answer the user's question directly, naturally and "
            "concisely using the tool result below. Copy any figures EXACTLY as given — same digits, "
            "magnitude and units (e.g. 345,000,000 is 'about 345 million', never 'billion'); prefer the "
            "'formatted' value when present. Don't disclaim your expertise — just answer helpfully in a "
            "sentence or two."
        )
        syn_user = f"Question: {raw}\nTool called: {name}({json.dumps(args)})\nResult: {json.dumps(result)}"
        messages = [{"role": "system", "content": syn_system}]
        messages.extend(state.get("chat_context", []))
        messages.append({"role": "user", "content": syn_user})
        return {"tool_calls": calls, "generated_answer": invoke_text(gen, messages)}

    def internet_search(state: RAGState) -> RAGState:
        results = web_search(state.get("rewritten_query") or state["raw_query"], max_results=5)
        if not results:
            return {"search_results": [],
                    "generated_answer": "I couldn't reach the web search service just now. "
                    "Please try again, or ask me something from the finance knowledge base."}
        context = "\n".join(
            f"[{i+1}] {r['title']}\n{r['snippet']}\n({r['url']})" for i, r in enumerate(results))
        system = (
            "You are BookRAG. Answer the user's question using the web search results below. "
            "Write naturally and concisely, and cite sources inline like [1], [2]. If the results "
            "don't actually answer the question, say so briefly."
        )
        user = f"Question: {state['raw_query']}\n\nWeb results:\n{context}\n\nAnswer:"
        messages = [{"role": "system", "content": system}]
        messages.extend(state.get("chat_context", []))
        messages.append({"role": "user", "content": user})
        sources = [{"title": r["title"], "source": "web", "page": "", "url": r["url"],
                    "element_type": "web", "rrf_score": 0} for r in results]
        return {"search_results": results, "sources": sources,
                "generated_answer": invoke_text(gen, messages)}

    def build_final_answer(state: RAGState) -> RAGState:
        answer = state.get("generated_answer", "")
        route = state.get("route")
        if route == "rag":
            sources = [
                {"title": d.get("title", ""), "source": d.get("source", ""),
                 "page": d.get("page", ""), "element_type": d.get("element_type", "text"),
                 "rrf_score": d.get("rrf_score", 0),
                 "doc_id": d.get("doc_id", ""), "project_id": d.get("project_id", "")}
                for d in state.get("retrieved_docs", [])
            ]
            grounded = state.get("is_grounded", False)
            return {"final_answer": answer, "disclaimer": "" if grounded else DISCLAIMER,
                    "sources": sources}
        if route == "search":
            return {"final_answer": answer, "disclaimer": "", "sources": state.get("sources", [])}
        # tool / general
        return {"final_answer": answer, "disclaimer": "", "sources": []}

    # ---------------------------------------------------------------- graph
    def route_after_rewrite(state: RAGState) -> str:
        return {"general": "general_answer", "tool": "tool_call",
                "search": "internet_search"}.get(state["route"], "retrieve")

    def route_after_eval(state: RAGState) -> str:
        if state.get("is_grounded") or state.get("retry_count", 0) >= 1:
            return "cross_reference"
        return "expand_query"

    g = StateGraph(RAGState)
    for name, fn in [
        ("rewrite_and_route", rewrite_and_route), ("retrieve", retrieve),
        ("generate", generate), ("evaluate_grounding", evaluate_grounding),
        ("expand_query", expand_query), ("general_answer", general_answer),
        ("tool_call", tool_call), ("internet_search", internet_search),
        ("cross_reference", cross_reference), ("build_final_answer", build_final_answer),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "rewrite_and_route")
    g.add_conditional_edges("rewrite_and_route", route_after_rewrite, {
        "general_answer": "general_answer", "retrieve": "retrieve",
        "tool_call": "tool_call", "internet_search": "internet_search",
    })
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "evaluate_grounding")
    g.add_conditional_edges("evaluate_grounding", route_after_eval,
                            {"expand_query": "expand_query", "cross_reference": "cross_reference"})
    g.add_edge("cross_reference", "build_final_answer")
    g.add_edge("expand_query", "retrieve")
    g.add_edge("general_answer", "build_final_answer")
    g.add_edge("tool_call", "build_final_answer")
    g.add_edge("internet_search", "build_final_answer")
    g.add_edge("build_final_answer", END)
    return g.compile()
