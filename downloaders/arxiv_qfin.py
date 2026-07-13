"""arXiv quantitative-finance & economics papers (native PDFs, equations/plots/tables).

Official API, no key. Docs: https://info.arxiv.org/help/api/
Multimodal value: dense math, figures, and results tables — a good stress test.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .common import Ctx, RateLimiter, save_from_url

SOURCE = "arxiv_qfin"
_NS = {"a": "http://www.w3.org/2005/Atom"}

# Spread across every q-fin subfield (+ general economics) for topical variety.
CATEGORIES = [
    "q-fin.PM", "q-fin.PR", "q-fin.RM", "q-fin.TR", "q-fin.CP",
    "q-fin.GN", "q-fin.MF", "q-fin.ST", "q-fin.EC", "econ.GN",
]
PAGE = 50


def fetch(ctx: Ctx, limit: int) -> int:
    # arXiv asks for ~1 request per 3s; one shared limiter covers query + download.
    rate = RateLimiter(3.5)
    s = ctx.session()
    added = 0
    for cat in CATEGORIES:
        if added >= limit:
            break
        start = 0
        while added < limit and start < 300:
            rate.wait()
            q = (
                "https://export.arxiv.org/api/query?"
                f"search_query=cat:{cat}&start={start}&max_results={PAGE}"
                "&sortBy=submittedDate&sortOrder=descending"
            )
            try:
                root = ET.fromstring(s.get(q, timeout=60).text)
            except Exception as e:  # noqa: BLE001
                ctx.log(f"  ! arxiv query failed for {cat}: {e}")
                break
            entries = root.findall("a:entry", _NS)
            if not entries:
                break
            for e in entries:
                if added >= limit:
                    break
                title = " ".join(e.findtext("a:title", default="", namespaces=_NS).split())
                pdf = next(
                    (lk.get("href") for lk in e.findall("a:link", _NS) if lk.get("title") == "pdf"),
                    None,
                )
                if not pdf:
                    continue
                if save_from_url(ctx, SOURCE, pdf, title, s, rate, extra={"category": cat}):
                    added += 1
            start += PAGE
    return added
