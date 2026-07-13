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

import config
from utils.llm import make_llm, invoke_text, parse_json
from utils.retrieval import get_retriever


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


DISCLAIMER = (
    "⚠️ Note: I could not fully verify this answer against the source "
    "documents after two attempts. Some claims may not be directly grounded in the "
    "texts. Please treat this response with caution and consider cross-referencing "
    "the originals. Feel free to rephrase your question for a more targeted search."
)


def _format_docs(docs: list[dict]) -> str:
    blocks = []
    for d in docs:
        kind = "TABLE" if d.get("element_type") == "table" else "TEXT"
        page = f", p.{d['page']}" if d.get("page") else ""
        text = d["text"]
        if len(text) > config.EXCERPT_CHARS:          # trim to keep the token budget low
            text = text[:config.EXCERPT_CHARS] + " …"
        blocks.append(f"[{kind}] Source: {d.get('title', 'document')} ({d.get('source', '')}{page})\n{text}\n---")
    return "\n".join(blocks)


def build_graph():
    """Compile and return the LangGraph app. LLM clients are created once here."""
    router = make_llm(config.MODEL_ROUTER, temperature=0.0)
    general_llm = make_llm(config.MODEL_GENERAL, temperature=0.4)
    heavy = make_llm(config.MODEL_HEAVY, temperature=0.1)
    retriever = get_retriever()

    # ---------------------------------------------------------------- nodes
    def rewrite_and_route(state: RAGState) -> RAGState:
        raw = state["raw_query"]
        system = "You are a query processor. Respond ONLY with valid JSON, no explanation, no markdown fences."
        user = (
            "Given the user query below, do two things:\n"
            "1. Rewrite it to be clearer and more search-friendly for a finance/business/"
            "wealth document collection. Keep the meaning identical.\n"
            "2. Classify the route:\n"
            "   - \"general\" if conversational (hi, thanks, who made you, what can you do).\n"
            "   - \"rag\" if about finance, wealth, investing, companies, markets, or any topic "
            "answerable from documents.\n"
            'Respond ONLY with: {"rewritten_query": "...", "route": "general or rag"}\n\n'
            f"User query: {raw}"
        )
        data = parse_json(invoke_text(router, [
            {"role": "system", "content": system}, {"role": "user", "content": user},
        ]), default={})
        route = data.get("route", "rag")
        return {
            "rewritten_query": data.get("rewritten_query", raw) or raw,
            "route": "general" if route == "general" else "rag",
            "retry_count": 0,
        }

    def retrieve(state: RAGState) -> RAGState:
        if state.get("retry_count", 0) == 0:
            docs = retriever.retrieve(state["rewritten_query"])
            return {"retrieved_docs": docs, "first_attempt_docs": docs}
        docs = retriever.retrieve(state["expanded_query"], extra_docs=state.get("first_attempt_docs"))
        return {"retrieved_docs": docs}

    def generate(state: RAGState) -> RAGState:
        docs = state["retrieved_docs"]
        system = (
            "You are a knowledgeable assistant specialising in finance, business, and "
            "wealth-building. Answer using ONLY the provided excerpts below. Some excerpts "
            "are TABLES (Markdown) — read them carefully for figures. If the excerpts do not "
            "contain enough information, say so honestly rather than guessing. Be thorough and "
            "cite the source document name when referencing specific advice or data."
        )
        user = (
            f"Question: {state['rewritten_query']}\n\nDocument excerpts:\n{_format_docs(docs)}\n\n"
            "Answer based strictly on the excerpts above:"
        )
        messages = [{"role": "system", "content": system}]
        messages.extend(state.get("chat_context", []))
        messages.append({"role": "user", "content": user})
        return {"generated_answer": invoke_text(heavy, messages)}

    def evaluate_grounding(state: RAGState) -> RAGState:
        system = (
            "You are a strict fact-checker. Verify that every factual claim in the answer is "
            "directly supported by the provided source excerpts. Respond ONLY with valid JSON, "
            "no explanation, no markdown fences."
        )
        user = (
            f"Answer to evaluate:\n{state['generated_answer']}\n\n"
            f"Source excerpts used:\n{_format_docs(state['retrieved_docs'])}\n\n"
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
            "You are a helpful, friendly assistant for a finance/business knowledge base. "
            "Answer conversationally and concisely. You may answer general finance questions "
            "if the user is curious."
        )
        messages = [{"role": "system", "content": system}]
        messages.extend(state.get("chat_context", []))
        messages.append({"role": "user", "content": state["raw_query"]})
        return {"generated_answer": invoke_text(general_llm, messages)}

    def build_final_answer(state: RAGState) -> RAGState:
        answer = state.get("generated_answer", "")
        if state.get("route") == "rag":
            sources = [
                {"title": d.get("title", ""), "source": d.get("source", ""),
                 "page": d.get("page", ""), "element_type": d.get("element_type", "text"),
                 "rrf_score": d.get("rrf_score", 0)}
                for d in state.get("retrieved_docs", [])
            ]
            grounded = state.get("is_grounded", False)
            return {
                "final_answer": answer,
                "disclaimer": "" if grounded else DISCLAIMER,
                "sources": sources,
            }
        return {"final_answer": answer, "disclaimer": "", "sources": []}

    # ---------------------------------------------------------------- graph
    def route_after_rewrite(state: RAGState) -> str:
        return "general_answer" if state["route"] == "general" else "retrieve"

    def route_after_eval(state: RAGState) -> str:
        if state.get("is_grounded") or state.get("retry_count", 0) >= 1:
            return "build_final_answer"
        return "expand_query"

    g = StateGraph(RAGState)
    for name, fn in [
        ("rewrite_and_route", rewrite_and_route), ("retrieve", retrieve),
        ("generate", generate), ("evaluate_grounding", evaluate_grounding),
        ("expand_query", expand_query), ("general_answer", general_answer),
        ("build_final_answer", build_final_answer),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "rewrite_and_route")
    g.add_conditional_edges("rewrite_and_route", route_after_rewrite,
                            {"general_answer": "general_answer", "retrieve": "retrieve"})
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "evaluate_grounding")
    g.add_conditional_edges("evaluate_grounding", route_after_eval,
                            {"expand_query": "expand_query", "build_final_answer": "build_final_answer"})
    g.add_edge("expand_query", "retrieve")
    g.add_edge("general_answer", "build_final_answer")
    g.add_edge("build_final_answer", END)
    return g.compile()
