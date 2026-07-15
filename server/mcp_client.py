"""MCP client — connects BookRAG's agent to external MCP servers (Model Context Protocol).

Reads `mcp_config.json` (standard `mcpServers` shape), discovers each server's tools over
stdio JSON-RPC, and lets the agent call them. Tools are namespaced `mcp:<server>:<tool>`
and merged into the tool-selection menu alongside the built-in tools.

Design: a fresh stdio session per operation (connect → call → close). Slightly slower than
a pooled session but stateless and robust — no subprocess lifecycle bugs across requests.
Everything degrades gracefully: if the SDK is missing or a server is unreachable, MCP is
simply reported as unavailable and the rest of the app is unaffected.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "mcp_config.json"

_tools_cache: list[dict] | None = None


def _run_async(coro):
    """Run a coroutine from sync code, whether or not an event loop is already running.

    FastAPI's startup hook and async routes execute inside uvicorn's loop, where
    asyncio.run() raises; LangGraph's sync nodes run in worker threads, where it's fine.
    When a loop is live we hand the coroutine to a fresh thread with its own loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)          # no running loop in this thread
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text()).get("mcpServers", {}) or {}
    except Exception:
        return {}


def _params(cfg: dict):
    """Build StdioServerParameters, resolving 'python' and relative script paths."""
    from mcp import StdioServerParameters
    command = cfg.get("command", "")
    if command in ("python", "python3"):
        command = sys.executable
    args = []
    for a in cfg.get("args", []):
        p = Path(a)
        if a.endswith(".py") and not p.is_absolute():
            a = str(ROOT / a)
        args.append(a)
    env = {**os.environ, **(cfg.get("env") or {})}
    return StdioServerParameters(command=command, args=args, env=env)


async def _with_session(cfg: dict, fn):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    async with stdio_client(_params(cfg)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


async def _discover() -> list[dict]:
    tools: list[dict] = []
    for name, cfg in _load_config().items():
        try:
            async def _list(session):
                return await session.list_tools()
            res = await asyncio.wait_for(_with_session(cfg, _list), timeout=30)
            for t in res.tools:
                # keep the FULL description (collapsed) — it carries argument conventions
                # the model needs (e.g. "pass 7 for 7%"), not just the first line.
                desc = " ".join((t.description or "").split())[:400]
                tools.append({
                    "server": name,
                    "name": t.name,
                    "qualified": f"mcp:{name}:{t.name}",
                    "description": desc,
                    "schema": getattr(t, "inputSchema", {}) or {},
                })
        except Exception as e:  # noqa: BLE001
            print(f"[mcp] server '{name}' unavailable: {type(e).__name__}: {e}")
    return tools


def list_tools(force: bool = False) -> list[dict]:
    """Discovered MCP tools (cached). Safe to call from sync code."""
    global _tools_cache
    if _tools_cache is not None and not force:
        return _tools_cache
    try:
        _tools_cache = _run_async(_discover())
    except Exception as e:  # noqa: BLE001
        # leave the cache unset so a later call retries instead of caching a failure
        print(f"[mcp] discovery failed: {type(e).__name__}: {e}")
        return []
    return _tools_cache


def _fmt_args(schema: dict) -> str:
    """Render args with their types + required-ness so the model passes correct values."""
    props = (schema or {}).get("properties", {}) or {}
    required = set((schema or {}).get("required", []) or [])
    parts = []
    for k, v in props.items():
        t = v.get("type", "any")
        parts.append(f"{k}: {t}" + ("" if k in required else " (optional)"))
    return ", ".join(parts)


def menu() -> str:
    """Menu lines for the tool-selection prompt (empty string if no MCP tools)."""
    lines = []
    for t in list_tools():
        lines.append(f'- {t["qualified"]}({_fmt_args(t["schema"])}): {t["description"]} [via MCP]')
    return "\n".join(lines)


def call_tool(server: str, tool: str, args: dict) -> dict:
    """Call an MCP tool. Returns a JSON-serialisable dict (never raises)."""
    cfg = _load_config().get(server)
    if not cfg:
        return {"error": f"unknown MCP server '{server}'"}

    async def _call(session):
        return await session.call_tool(tool, args or {})

    try:
        res = _run_async(asyncio.wait_for(_with_session(cfg, _call), timeout=60))
    except Exception as e:  # noqa: BLE001
        return {"error": f"MCP call failed: {type(e).__name__}: {e}"}

    texts = []
    for block in getattr(res, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    raw = "\n".join(texts).strip()
    try:                       # most MCP tools return JSON text
        return json.loads(raw)
    except Exception:
        return {"result": raw or "(no content)"}


def status() -> dict:
    """Connected servers + their tools (for the /api/mcp endpoint & the UI)."""
    tools = list_tools()
    servers: dict[str, list] = {}
    for t in tools:
        servers.setdefault(t["server"], []).append(
            {"name": t["name"], "description": t["description"]})
    return {
        "connected": len(servers),
        "tool_count": len(tools),
        "servers": [{"name": k, "tools": v} for k, v in servers.items()],
    }
