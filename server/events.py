"""Structured database logging for every major step + analytics aggregation.

Every request gets a correlation_id; each pipeline node, tool/MCP call, auth event and
error is written to `event_logs`. Logging is strictly best-effort — it must never break a
user request.

Aggregation is done in Python over a recent window rather than with SQL JSON functions,
so the same code works on both SQLite (dev) and Postgres (prod).
"""
from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict

from db.base import session_scope
from db.models import EventLog

# Steps that represent a pipeline node (vs. request/auth/error bookkeeping)
NODE_STEPS = {"rewrite_and_route", "retrieve", "generate", "evaluate_grounding",
              "expand_query", "general_answer", "tool_call", "internet_search",
              "build_final_answer"}


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


def log_event(step: str, *, correlation_id: str = "", user_id: str = "", chat_id: str = "",
              payload: dict | None = None, latency_ms: int = 0, level: str = "info") -> None:
    """Write one structured event. Never raises."""
    try:
        with session_scope() as s:
            s.add(EventLog(
                correlation_id=correlation_id, user_id=user_id, chat_id=chat_id,
                step=step, payload=json.dumps(payload or {}, default=str)[:4000],
                latency_ms=int(latency_ms or 0), level=level, ts=time.time(),
            ))
    except Exception:  # noqa: BLE001 - logging must never break the request
        pass


def _row(r: EventLog) -> dict:
    try:
        payload = json.loads(r.payload)
    except Exception:
        payload = {}
    return {"id": r.id, "correlation_id": r.correlation_id, "user_id": r.user_id,
            "chat_id": r.chat_id, "step": r.step, "payload": payload,
            "latency_ms": r.latency_ms, "level": r.level, "ts": r.ts}


def recent(limit: int = 100, step: str | None = None, level: str | None = None) -> list[dict]:
    with session_scope() as s:
        q = s.query(EventLog).order_by(EventLog.id.desc())
        if step:
            q = q.filter(EventLog.step == step)
        if level:
            q = q.filter(EventLog.level == level)
        return [_row(r) for r in q.limit(min(limit, 500)).all()]


def analytics(window: int = 2000) -> dict:
    """Aggregate the most recent `window` events into dashboard stats."""
    with session_scope() as s:
        rows = [_row(r) for r in
                s.query(EventLog).order_by(EventLog.id.desc()).limit(window).all()]

    done = [r for r in rows if r["step"] == "done"]
    errors = [r for r in rows if r["level"] == "error"]
    node_rows = [r for r in rows if r["step"] in NODE_STEPS]

    routes: dict[str, int] = defaultdict(int)
    grounded = unverified = retried = 0
    tools: dict[str, int] = defaultdict(int)
    mcp_calls = web_searches = 0
    latencies: list[int] = []

    for r in done:
        p = r["payload"]
        routes[p.get("route") or "?"] += 1
        if p.get("route") == "rag":
            if p.get("is_grounded"):
                grounded += 1
            else:
                unverified += 1
        if p.get("retry_count"):
            retried += 1
        if p.get("tool"):
            tools[p["tool"]] += 1
            if str(p.get("via", "")).startswith("mcp"):
                mcp_calls += 1
        if p.get("n_web"):
            web_searches += 1
        if r["latency_ms"]:
            latencies.append(r["latency_ms"])

    per_node: dict[str, list[int]] = defaultdict(list)
    for r in node_rows:
        per_node[r["step"]].append(r["latency_ms"])
    node_latency = sorted(
        ({"step": k, "avg_ms": round(sum(v) / len(v)), "count": len(v)}
         for k, v in per_node.items() if v),
        key=lambda x: -x["avg_ms"])

    users = {r["user_id"] for r in rows if r["user_id"]}
    return {
        "totals": {
            "queries": len(done),
            "events": len(rows),
            "errors": len(errors),
            "users": len(users),
            "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
            "tool_calls": sum(tools.values()),
            "mcp_calls": mcp_calls,
            "web_searches": web_searches,
        },
        "routes": dict(routes),
        "grounding": {"verified": grounded, "unverified": unverified, "retried": retried},
        "node_latency": node_latency,
        "top_tools": sorted(({"name": k, "count": v} for k, v in tools.items()),
                            key=lambda x: -x["count"])[:8],
        "recent": rows[:40],
    }
