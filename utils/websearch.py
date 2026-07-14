"""Keyless internet search via DuckDuckGo (ddgs). Graceful if the package is missing."""
from __future__ import annotations


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Return [{title, snippet, url}]. Empty list on any failure (never raises)."""
    try:
        from ddgs import DDGS
    except Exception:
        try:
            from duckduckgo_search import DDGS  # older package name
        except Exception:
            return []
    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=max_results))
        return [{"title": h.get("title", ""), "snippet": h.get("body", ""),
                 "url": h.get("href", "")} for h in hits]
    except Exception:
        return []


def available() -> bool:
    try:
        import ddgs  # noqa: F401
        return True
    except Exception:
        try:
            import duckduckgo_search  # noqa: F401
            return True
        except Exception:
            return False
