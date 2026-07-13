"""Runs the LangGraph pipeline and turns it into a live event stream for the UI.

Emits, in real time:
  node_start / node_end (with per-node duration + a human summary),
  token (answer streamed for a typing effect), sources, trace, done | error.
The active-node inference mirrors the pipeline's edges so the flowchart lights up
correctly through conditional routes and the retry loop.
"""
from __future__ import annotations

import asyncio
import re
import time

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        from pipeline import build_graph
        _graph = build_graph()
    return _graph


def warmup() -> None:
    get_graph()


def _next_node(node: str, s: dict) -> str | None:
    if node == "rewrite_and_route":
        return "general_answer" if s.get("route") == "general" else "retrieve"
    if node == "retrieve":
        return "generate"
    if node == "generate":
        return "evaluate_grounding"
    if node == "evaluate_grounding":
        return "build_final_answer" if (s.get("is_grounded") or s.get("retry_count", 0) >= 1) else "expand_query"
    if node == "expand_query":
        return "retrieve"
    if node == "general_answer":
        return "build_final_answer"
    return None


def _summary(node: str, s: dict) -> str:
    if node == "rewrite_and_route":
        return f"route → {s.get('route', '?')} · rewrote query"
    if node == "retrieve":
        return f"{len(s.get('retrieved_docs', []))} excerpts fused (dense + BM25 → RRF)"
    if node == "generate":
        return f"drafted {len(s.get('generated_answer', ''))} chars from excerpts"
    if node == "evaluate_grounding":
        g = s.get("is_grounded")
        return f"{'✓ grounded' if g else '✗ unverified'} · {s.get('grounding_reason', '')[:60]}"
    if node == "expand_query":
        return f"expanded query, retrying retrieval"
    if node == "general_answer":
        return "conversational reply drafted"
    if node == "build_final_answer":
        return f"{len(s.get('sources', []))} sources attached"
    return ""


async def run_stream(query: str, context: list[dict]):
    graph = get_graph()
    state: dict = {}
    t_prev = time.perf_counter()

    yield {"type": "node_start", "node": "rewrite_and_route"}
    try:
        async for update in graph.astream(
            {"raw_query": query, "chat_context": context}, stream_mode="updates"
        ):
            for node, delta in update.items():
                if not isinstance(delta, dict):
                    continue
                now = time.perf_counter()
                dur_ms = int((now - t_prev) * 1000)
                t_prev = now
                state.update(delta)
                yield {"type": "node_end", "node": node,
                       "dur_ms": dur_ms, "summary": _summary(node, state)}
                nxt = _next_node(node, state)
                if nxt:
                    yield {"type": "node_start", "node": nxt}
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
        return

    answer = state.get("final_answer") or state.get("generated_answer") or "_No answer produced._"
    sources = state.get("sources", [])
    trace = {
        "route": state.get("route", "rag"),
        "rewritten_query": state.get("rewritten_query", ""),
        "retry_count": state.get("retry_count", 0),
        "is_grounded": state.get("is_grounded"),
        "grounding_reason": state.get("grounding_reason", ""),
    }

    yield {"type": "sources", "sources": sources}
    yield {"type": "trace", "trace": trace}

    # Stream the answer for a live typing effect (fast).
    tokens = re.findall(r"\S+\s*", answer)
    buf, i = "", 0
    for tok in tokens:
        buf += tok
        i += 1
        if i % 3 == 0:
            yield {"type": "token", "text": buf}
            buf = ""
            await asyncio.sleep(0.01)
    if buf:
        yield {"type": "token", "text": buf}

    yield {"type": "done", "answer": answer, "sources": sources, "trace": trace}
