"""BookRAG FastAPI backend.

Endpoints:
  GET  /api/health                 liveness + provider/model info
  GET  /api/nodes                  pipeline node metadata (for the flowchart)
  GET  /api/corpus                 ingest stats (for the dashboard)
  GET  /api/chats                  list chats
  POST /api/chats                  create chat
  GET  /api/chats/{id}             chat + messages
  DELETE /api/chats/{id}           delete chat
  POST /api/chats/{id}/stream      SSE: live pipeline execution + streamed answer
"""
from __future__ import annotations

import json
from pathlib import Path

import re
import uuid

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

import config
from auth.deps import get_current_user_id
from server import events, memory, project_store, rag_service, store
from server.nodes_meta import NODES
from utils.parsing import AUDIO_EXTS, IMAGE_EXTS

UPLOAD_DIR = config.ROOT / "uploads"

app = FastAPI(title="BookRAG API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    store.init_db()
    try:
        rag_service.warmup()  # load Chroma + BGE + compile graph once
    except Exception as e:  # noqa: BLE001
        print(f"[warmup] deferred: {e}")
    try:  # discover MCP tools once so the first tool call is fast
        from server import mcp_client
        st = mcp_client.status()
        print(f"[mcp] {st['connected']} server(s), {st['tool_count']} tool(s) discovered")
    except Exception as e:  # noqa: BLE001
        print(f"[mcp] discovery skipped: {e}")


# ------------------------------------------------------------------ meta
@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "provider": config.PROVIDER,
        "mock": config.MOCK_LLM,
        "models": {"router": config.MODEL_ROUTER, "general": config.MODEL_GENERAL,
                   "heavy": config.MODEL_HEAVY},
        "endpoint": config.LLM_BASE_URL,
    }


@app.get("/api/nodes")
def nodes() -> list:
    return NODES


@app.get("/api/corpus")
def corpus() -> dict:
    if config.INGEST_STATE.exists():
        return json.loads(config.INGEST_STATE.read_text())
    return {}


@app.get("/api/analytics")
def analytics(user_id: str = Depends(get_current_user_id)) -> dict:
    """Aggregated observability stats built from the event_logs table."""
    return events.analytics()


@app.get("/api/logs")
def logs(limit: int = 100, step: str | None = None, level: str | None = None,
         user_id: str = Depends(get_current_user_id)) -> list:
    """Recent structured events (every major pipeline step is logged)."""
    return events.recent(limit=limit, step=step, level=level)


@app.get("/api/mcp")
def mcp_status() -> dict:
    """Connected MCP servers and the tools they expose to the agent."""
    try:
        from server import mcp_client
        return mcp_client.status()
    except Exception as e:  # noqa: BLE001
        return {"connected": 0, "tool_count": 0, "servers": [], "error": str(e)}


# ------------------------------------------------------------------ chats (auth-protected)
@app.get("/api/chats")
def list_chats(user_id: str = Depends(get_current_user_id)) -> list:
    return store.list_chats(user_id)


@app.post("/api/chats")
async def create_chat(request: Request, user_id: str = Depends(get_current_user_id)) -> dict:
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    project_id = (body or {}).get("project_id", "") or ""
    if project_id and not store.get_project(project_id, user_id):
        raise HTTPException(404, "project not found")
    return store.create_chat(user_id, project_id=project_id)


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, user_id: str = Depends(get_current_user_id)) -> dict:
    chat = store.get_chat(chat_id, user_id)
    if not chat:
        raise HTTPException(404, "chat not found")
    return {"chat": chat, "messages": store.get_messages(chat_id)}


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, user_id: str = Depends(get_current_user_id)) -> dict:
    store.delete_chat(chat_id, user_id)
    return {"ok": True}


# ------------------------------------------------------------------ projects
@app.get("/api/projects")
def list_projects(user_id: str = Depends(get_current_user_id)) -> list:
    return store.list_projects(user_id)


@app.post("/api/projects")
async def create_project(request: Request, user_id: str = Depends(get_current_user_id)) -> dict:
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "project name required")
    return store.create_project(user_id, name, (body.get("description") or "").strip())


@app.get("/api/projects/{pid}")
def get_project(pid: str, user_id: str = Depends(get_current_user_id)) -> dict:
    p = store.get_project(pid, user_id)
    if not p:
        raise HTTPException(404, "project not found")
    return {"project": p, "files": store.list_files(pid)}


@app.delete("/api/projects/{pid}")
def delete_project(pid: str, user_id: str = Depends(get_current_user_id)) -> dict:
    if not store.get_project(pid, user_id):
        raise HTTPException(404, "project not found")
    project_store.delete_project(pid)
    store.delete_project(pid, user_id)
    return {"ok": True}


@app.post("/api/projects/{pid}/files")
async def upload_file(pid: str, file: UploadFile = File(...),
                      user_id: str = Depends(get_current_user_id)) -> dict:
    if not store.get_project(pid, user_id):
        raise HTTPException(404, "project not found")
    safe = re.sub(r"[^\w.\- ]", "_", file.filename or "upload")[:200]
    fid = uuid.uuid4().hex[:16]
    dest_dir = UPLOAD_DIR / pid
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{fid}_{safe}"
    data = await file.read()
    dest.write_bytes(data)

    ext = dest.suffix.lower()
    kind = "image" if ext in IMAGE_EXTS else "audio" if ext in AUDIO_EXTS else "doc"
    rec = store.add_file(pid, safe, str(dest), kind, len(data))
    doc_id = rec["id"]
    # Ingest inline (parse -> chunk -> embed -> project vectors). Fine for demo-sized files.
    try:
        n = project_store.ingest_file(pid, doc_id, safe, str(dest))
        store.set_file_status(doc_id, "ready", chunks=n)
        rec["status"], rec["chunks"] = "ready", n
    except Exception as e:  # noqa: BLE001
        store.set_file_status(doc_id, "error", error=str(e))
        rec["status"], rec["error"] = "error", str(e)
    return rec


@app.get("/api/projects/{pid}/files/{fid}/raw")
def raw_file(pid: str, fid: str, user_id: str = Depends(get_current_user_id)):
    if not store.get_project(pid, user_id):
        raise HTTPException(404, "project not found")
    f = store.get_file(fid)
    if not f or f["project_id"] != pid:
        raise HTTPException(404, "file not found")
    return FileResponse(f["path"], filename=f["filename"])


# ------------------------------------------------------------------ streaming chat
@app.post("/api/chats/{chat_id}/stream")
async def stream_chat(chat_id: str, request: Request,
                      user_id: str = Depends(get_current_user_id)):
    chat = store.get_chat(chat_id, user_id)
    if not chat:
        raise HTTPException(404, "chat not found")
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "empty message")

    # Title the chat from its first user message.
    if chat["title"] == "New chat" and not store.get_messages(chat_id):
        store.rename_chat(chat_id, memory.title_from(message))

    store.add_message(chat_id, "user", message)
    context = memory.build_context(chat_id)
    project_id = chat.get("project_id", "") or ""

    cid = events.new_correlation_id()
    events.log_event("request", correlation_id=cid, user_id=user_id, chat_id=chat_id,
                     payload={"message": message[:200], "project_id": project_id})

    async def event_gen():
        async for ev in rag_service.run_stream(message, context, project_id=project_id):
            # --- structured DB logging of every major step ---
            if ev["type"] == "node_end":
                events.log_event(ev["node"], correlation_id=cid, user_id=user_id,
                                 chat_id=chat_id, latency_ms=ev.get("dur_ms", 0),
                                 payload={"summary": ev.get("summary", "")})
            elif ev["type"] == "error":
                events.log_event("error", correlation_id=cid, user_id=user_id,
                                 chat_id=chat_id, level="error",
                                 payload={"message": ev.get("message", "")})
            elif ev["type"] == "done":
                rec = ev.get("record") or {}
                tc = (rec.get("tool_calls") or [{}])[0]
                events.log_event("done", correlation_id=cid, user_id=user_id, chat_id=chat_id,
                                 latency_ms=rec.get("total_ms", 0),
                                 payload={"route": rec.get("route"),
                                          "is_grounded": rec.get("is_grounded"),
                                          "retry_count": rec.get("retry_count", 0),
                                          "tool": tc.get("name"), "via": tc.get("via"),
                                          "n_sources": len(rec.get("sources") or []),
                                          "n_web": len(rec.get("search_results") or []),
                                          "model": rec.get("model")})
                # persist the full run record (superset of trace) so the inspector
                # works after a reload too
                store.add_message(chat_id, "assistant", ev["answer"],
                                  ev.get("sources"), ev.get("record") or ev.get("trace"))
            yield {"data": json.dumps(ev)}
        # Post-response snapshotting (best-effort; adds no perceived latency).
        try:
            memory.maybe_summarize(chat_id)
            memory.maybe_update_profile(chat_id)
        except Exception:  # noqa: BLE001
            pass

    return EventSourceResponse(event_gen())


# ------------------------------------------------------------------ static (production build)
_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="static")
