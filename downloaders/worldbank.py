"""World Bank Documents & Reports (open-access economic/finance PDFs).

WDS API, no key: https://documents.worldbank.org/  (api/v2/wds)
Multimodal value: charts, data tables, infographics in professionally designed PDFs.
Returns direct `pdfurl`s, so this is one of the most reliable sources here.
"""
from __future__ import annotations

from .common import Ctx, RateLimiter, save_from_url

SOURCE = "worldbank"
ROWS = 50
QTERM = "finance"  # keep the pull on-topic for a wealth/finance RAG


def fetch(ctx: Ctx, limit: int) -> int:
    rate = RateLimiter(1.0)
    s = ctx.session()
    added = 0
    offset = 0
    while added < limit and offset < 800:
        rate.wait()
        url = (
            "https://search.worldbank.org/api/v2/wds?format=json"
            f"&rows={ROWS}&os={offset}&fl=docdt,display_title,pdfurl&qterm={QTERM}"
        )
        try:
            data = s.get(url, timeout=60).json()
        except Exception as e:  # noqa: BLE001
            ctx.log(f"  ! WDS query failed: {e}")
            break

        docs = data.get("documents", {})
        items = [v for k, v in docs.items() if k != "facets" and isinstance(v, dict)]
        if not items:
            break
        for d in items:
            if added >= limit:
                break
            pdf = d.get("pdfurl")
            if not pdf:
                continue
            title = d.get("display_title") or "World Bank document"
            if save_from_url(ctx, SOURCE, pdf, title, s, rate, extra={"docdt": d.get("docdt")}):
                added += 1
        offset += ROWS
    return added
