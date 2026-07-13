"""Public-domain finance/economics texts from the Internet Archive (scanned PDFs).

Archive.org advanced-search + metadata APIs, no key.
Multimodal value: many are SCANNED image PDFs -> the OCR path for your ingest upgrade.
These are safe to redistribute, which matters for a sellable product.
"""
from __future__ import annotations

import urllib.parse

from .common import Ctx, RateLimiter, save_from_url

SOURCE = "public_domain"
# Exclude the borrowable/lending collections (inlibrary/printdisabled) -- those
# return 401/403 on direct download and are not freely redistributable.
QUERY = (
    "subject:(finance OR investing OR economics) AND mediatype:texts "
    "AND NOT collection:(inlibrary OR printdisabled)"
)


def fetch(ctx: Ctx, limit: int) -> int:
    rate = RateLimiter(1.0)
    s = ctx.session()
    added = 0
    page = 1
    while added < limit and page <= 12:
        rate.wait()
        search = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(
            {"q": QUERY, "fl[]": "identifier", "rows": 50, "page": page, "output": "json"},
            doseq=True,
        )
        try:
            docs = s.get(search, timeout=60).json().get("response", {}).get("docs", [])
        except Exception as e:  # noqa: BLE001
            ctx.log(f"  ! archive.org search failed: {e}")
            break
        if not docs:
            break

        for d in docs:
            if added >= limit:
                break
            ident = d.get("identifier")
            if not ident:
                continue
            rate.wait()
            try:
                meta = s.get(f"https://archive.org/metadata/{ident}", timeout=60).json()
            except Exception:  # noqa: BLE001
                continue
            md = meta.get("metadata", {}) or {}
            if str(md.get("access-restricted-item", "")).lower() == "true":
                continue  # belt-and-suspenders: skip anything still flagged restricted
            pdfs = [f for f in meta.get("files", []) if f.get("name", "").lower().endswith(".pdf")]
            if not pdfs:
                continue  # only djvu/epub/txt available -> skip
            pdfs.sort(key=lambda f: int(f.get("size", "0") or 0), reverse=True)
            fname = pdfs[0]["name"]
            title = md.get("title") or ident
            if isinstance(title, list):
                title = title[0]
            url = f"https://archive.org/download/{ident}/{urllib.parse.quote(fname)}"
            if save_from_url(ctx, SOURCE, url, title, s, rate, extra={"archive_id": ident}):
                added += 1
        page += 1
    return added
