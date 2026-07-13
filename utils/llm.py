"""LLM client factory + robust JSON parsing.

Provider-agnostic: any OpenAI-compatible endpoint works (local Ollama, OpenAI, Groq,
Together, vLLM). Configure via env (see config.py / .env.example). Structured outputs
are done with plain-text + defensive JSON parsing (no tool-calling), per spec.
"""
from __future__ import annotations

import json
import re
import time
from types import SimpleNamespace
from typing import Any

from langchain_openai import ChatOpenAI

import config


class MockChat:
    """Deterministic, network-free stand-in for a chat model.

    Inspects the prompt to return the right shape for each pipeline node, so the whole
    LangGraph runs (and the streaming UI can be built/verified) with no API key.
    Enabled via BOOKRAG_MOCK_LLM=1.
    """

    def __init__(self, model: str = "mock") -> None:
        self.model = model

    def invoke(self, messages: list[dict], *_, **__):
        text = "\n".join(m.get("content", "") for m in messages if isinstance(m, dict))
        low = text.lower()
        time.sleep(0.15)  # simulate a little latency so timings look real

        if "respond only with" in low and "rewritten_query" in low:
            q = _extract_after(text, "User query:") or "your question"
            general = any(w in q.lower() for w in ("hi", "hello", "hey", "thanks", "thank you",
                                                   "who made you", "what can you do", "how are you"))
            return SimpleNamespace(content=json.dumps(
                {"rewritten_query": q.strip(), "route": "general" if general else "rag"}))

        if "strict fact-checker" in low:
            return SimpleNamespace(content=json.dumps(
                {"is_grounded": True, "reason": "All claims trace to the provided excerpts."}))

        if "query expander" in low:
            base = _extract_after(text, "The rewritten query:") or "query"
            return SimpleNamespace(content=f"{base} wealth investing returns risk strategy portfolio")

        if "summarise this conversation" in low:
            return SimpleNamespace(content="The user asked finance questions; answers were grounded in the corpus.")

        # Generation / general answer.
        titles = re.findall(r"Source: ([^\(\n]+)", text)
        cite = f" Based on {titles[0].strip()}." if titles else ""
        return SimpleNamespace(content=(
            "**[MOCK RESPONSE]** This is a placeholder answer generated without an LLM so the "
            "UI can be tested end-to-end." + cite + " Add a `GROQ_API_KEY` to `.env` (or set "
            "`BOOKRAG_MOCK_LLM=0`) to get real, grounded answers from the corpus."))


def _extract_after(text: str, marker: str) -> str:
    idx = text.find(marker)
    if idx == -1:
        return ""
    return text[idx + len(marker):].splitlines()[0].strip()


def make_llm(model: str, temperature: float = 0.2):
    if config.MOCK_LLM:
        return MockChat(model)
    return ChatOpenAI(
        model=model,
        base_url=config.llm_base_url(),
        api_key=config.LLM_API_KEY,
        temperature=temperature,
        timeout=config.LLM_TIMEOUT,
        max_retries=1,
        # NOTE: uncomment if your endpoint needs an auth header:
        # default_headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
    )


def invoke_text(llm: ChatOpenAI, messages: list[dict]) -> str:
    """Call the LLM with a list of {'role','content'} dicts; return the text."""
    return llm.invoke(messages).content.strip()


_FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)


def parse_json(text: str, default: Any = None) -> Any:
    """Strip markdown fences / prose and parse the first JSON object. Defensive."""
    if not text:
        return default
    cleaned = _FENCE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)  # grab first {...}
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return default
    return default
