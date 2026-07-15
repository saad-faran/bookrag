"""LLM client factory + robust JSON parsing.

Provider-agnostic: any OpenAI-compatible endpoint works (local Ollama, OpenAI, Groq,
Together, vLLM). Configure via env (see config.py / .env.example). Structured outputs
are done with plain-text + defensive JSON parsing (no tool-calling), per spec.
"""
from __future__ import annotations

import json
import os
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
        # the user's actual message (NOT the system prompt, which contains the tool menu)
        user_msg = ""
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "user":
                user_msg = m.get("content", "")
        time.sleep(0.15)  # simulate a little latency so timings look real

        if "respond only with" in low and "rewritten_query" in low:
            q = _extract_after(text, "User query:") or "your question"
            ql = q.lower()
            if any(w in ql for w in ("weather", "stock", "price", "convert", "calculate",
                                     "how much is", "% of", "crypto", "bitcoin", "what time",
                                     "compound interest", "double my money", "loan", "mortgage",
                                     "monthly payment")):
                route = "tool"
            elif any(w in ql for w in ("news", "latest", "today", "recent", "search the web",
                                       "current", "headlines")):
                route = "search"
            elif any(w in ql for w in ("hi", "hello", "hey", "thanks", "thank you",
                                       "who made you", "what can you do", "how are you")):
                route = "general"
            else:
                route = "rag"
            return SimpleNamespace(content=json.dumps({"rewritten_query": q.strip(), "route": route}))

        if "tool router" in low:  # tool selection
            q = user_msg.lower()   # match the USER's request, not the tool menu
            # MCP-served tools (namespaced mcp:<server>:<tool>)
            if "loan" in q or "mortgage" in q or "monthly payment" in q:
                return SimpleNamespace(content=json.dumps({
                    "tool": "mcp:finance:loan_payment",
                    "args": {"principal": 300000, "annual_rate_pct": 6.5, "years": 30}}))
            if "compound interest" in q or ("invest" in q and "grow" in q):
                return SimpleNamespace(content=json.dumps({
                    "tool": "mcp:finance:compound_interest",
                    "args": {"principal": 10000, "annual_rate_pct": 7, "years": 10}}))
            if "double" in q and ("money" in q or "investment" in q):
                return SimpleNamespace(content=json.dumps({
                    "tool": "mcp:finance:rule_of_72", "args": {"annual_rate_pct": 8}}))
            if "weather" in q:
                sel = {"tool": "get_weather", "args": {"location": "London"}}
            elif "convert" in q or " to eur" in q or " to usd" in q:
                sel = {"tool": "convert_currency", "args": {"amount": 100, "from_currency": "USD", "to_currency": "EUR"}}
            elif "bitcoin" in q or "crypto" in q:
                sel = {"tool": "get_crypto_price", "args": {"coin": "bitcoin", "vs_currency": "usd"}}
            elif "time" in q:
                sel = {"tool": "get_current_time", "args": {"timezone": "UTC"}}
            elif "stock" in q or "price" in q:
                sel = {"tool": "get_stock_quote", "args": {"symbol": "NVDA"}}
            else:
                sel = {"tool": "calculator", "args": {"expression": "2+2"}}
            return SimpleNamespace(content=json.dumps(sel))

        if "tool called:" in low or "tool result" in low:  # tool answer synthesis
            return SimpleNamespace(content="**[MOCK]** Here's the live result from the tool (real values "
                                           "appear when a GROQ_API_KEY is set).")

        if "web results:" in low:  # search answer synthesis
            return SimpleNamespace(content="**[MOCK]** Based on the web results [1][2], here's a concise "
                                           "summary (set a GROQ_API_KEY for real synthesis).")

        if "verify whether independent sources agree" in low:  # cross-reference node
            return SimpleNamespace(content=json.dumps({
                "consensus": "agree",
                "agreements": ["All sources describe the same core facts."],
                "conflicts": [],
                "note": "The retrieved sources are consistent with the answer."}))

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
        max_retries=int(os.getenv("BOOKRAG_LLM_RETRIES", "4")),
        # Disable Qwen3 thinking mode — prevents empty-output errors when the model
        # enters a reasoning loop that produces no output tokens.
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


def _merge_system_messages(messages: list[dict]) -> list[dict]:
    """Merge all contiguous system messages at the start of the list into one."""
    system_contents = []
    other_messages = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            if not other_messages:  # contiguous at the start
                content = msg.get("content", "")
                if content:
                    system_contents.append(content)
            else:
                other_messages.append({"role": "user", "content": f"[System Note] {msg.get('content')}"})
        else:
            other_messages.append(msg)
            
    if system_contents:
        merged_system = "\n\n".join(system_contents)
        return [{"role": "system", "content": merged_system}] + other_messages
    return other_messages


def invoke_text(llm: ChatOpenAI, messages: list[dict]) -> str:
    """Call the LLM with a list of {'role','content'} dicts; return the text."""
    merged = _merge_system_messages(messages)
    try:
        result = llm.invoke(merged).content.strip()
        if result:
            return result
        # Empty content — retry once with only the last user message to avoid
        # triggering a thinking-mode loop on complex prompts.
        last_user = next((m for m in reversed(merged) if m.get("role") == "user"), None)
        if last_user:
            result = llm.invoke([last_user]).content.strip()
        return result or ""
    except Exception as e:
        err = str(e)
        # Re-raise anything that isn't the empty-output error
        if "empty" not in err.lower() and "output text" not in err.lower():
            raise
        # Fallback: strip system message and retry bare
        bare = [m for m in merged if m.get("role") != "system"]
        return llm.invoke(bare or merged[-1:]).content.strip() if bare else ""


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
