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

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

import config
from auth.deps import get_current_user_id
from server import memory, rag_service, store
from server.nodes_meta import NODES

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


# ------------------------------------------------------------------ chats (auth-protected)
@app.get("/api/chats")
def list_chats(user_id: str = Depends(get_current_user_id)) -> list:
    return store.list_chats(user_id)


@app.post("/api/chats")
def create_chat(user_id: str = Depends(get_current_user_id)) -> dict:
    return store.create_chat(user_id)


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

    async def event_gen():
        async for ev in rag_service.run_stream(message, context):
            if ev["type"] == "done":
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
