"""Context assembly + snapshotting.

Two layers of long-term context, both kept bounded so prompts stay fast:
  1. Per-chat rolling SUMMARY  — old turns are compressed once they pile up.
  2. Cross-chat USER PROFILE   — durable facts about the user, learned over time.

build_context() stitches both (plus recent raw turns) into the messages the pipeline
sees. The snapshot updaters run AFTER a response is streamed, so they add no latency.
"""
from __future__ import annotations

from server import store
from utils.llm import make_llm
import config

_RECENT_RAW = 8          # keep this many latest turns verbatim
_SUMMARIZE_AFTER = 10    # compress once this many un-summarized turns accumulate
_PROFILE_EVERY = 3       # refresh the user profile every N user turns

_router = None


def _llm():
    global _router
    if _router is None:
        _router = make_llm(config.MODEL_ROUTER, temperature=0.0)
    return _router


def build_context(chat_id: str) -> list[dict]:
    """Messages sent to the pipeline: profile + chat summary + recent turns."""
    chat = store.get_chat(chat_id) or {}
    messages = store.get_messages(chat_id)
    ctx: list[dict] = []

    profile = store.get_user_profile(chat.get("user_id", "")).strip()
    if profile:
        ctx.append({"role": "system",
                    "content": f"What you know about this user (use it to personalise, don't recite): {profile}"})

    summary = (chat.get("summary") or "").strip()
    if summary:
        ctx.append({"role": "system", "content": f"Summary of earlier conversation: {summary}"})

    start = chat.get("unsummarized_start", 0)
    for m in messages[start:][-_RECENT_RAW:]:
        ctx.append({"role": m["role"], "content": m["content"]})
    return ctx


def maybe_summarize(chat_id: str) -> None:
    chat = store.get_chat(chat_id)
    if not chat:
        return
    messages = store.get_messages(chat_id)
    start = chat["unsummarized_start"]
    if len(messages) - start < _SUMMARIZE_AFTER:
        return
    batch = messages[start:start + _SUMMARIZE_AFTER]
    text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in batch)
    prompt = ("Summarise this conversation in 2-4 sentences, capturing key topics and "
              "conclusions:\n\n" + text)
    try:
        new = _llm().invoke([{"role": "user", "content": prompt}]).content.strip()
    except Exception:
        return
    prior = (chat["summary"] or "").strip()
    combined = f"{prior} Later: {new}" if prior else new
    store.update_summary(chat_id, combined, start + _SUMMARIZE_AFTER)


def maybe_update_profile(chat_id: str) -> None:
    chat = store.get_chat(chat_id)
    if not chat:
        return
    user_id = chat.get("user_id", "")
    messages = store.get_messages(chat_id)
    user_turns = [m for m in messages if m["role"] == "user"]
    if not user_turns or len(user_turns) % _PROFILE_EVERY != 0:
        return
    recent = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages[-8:])
    current = store.get_user_profile(user_id).strip() or "(nothing yet)"
    prompt = (
        "You maintain a concise profile of a user of a finance assistant. Given the current "
        "profile and the recent conversation, output an UPDATED profile (<=6 short bullet-style "
        "facts) capturing durable traits: their interests, goals, expertise level, risk appetite, "
        "companies/topics they care about. Keep only lasting facts, drop transient ones. Output "
        "only the profile text.\n\n"
        f"Current profile:\n{current}\n\nRecent conversation:\n{recent}"
    )
    try:
        updated = _llm().invoke([{"role": "user", "content": prompt}]).content.strip()
    except Exception:
        return
    if updated:
        store.set_user_profile(user_id, updated[:1200])


def title_from(first_message: str) -> str:
    t = " ".join(first_message.split())
    return (t[:44] + "…") if len(t) > 45 else t or "New chat"
