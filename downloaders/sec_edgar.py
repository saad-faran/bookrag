"""SEC EDGAR annual reports (10-K / 20-F) — the flagship finance corpus.

Official JSON APIs, no key; a real contact email in the User-Agent is required
(set CONTACT_EMAIL env var). Rate limit: <=10 req/s.
Multimodal value: dense financial-statement TABLES, footnotes, multi-column layouts.
Primary documents are HTML (.htm) — kept native here; upgrade ingest.py with an
HTML/table-aware loader when you resume chunking.
"""
from __future__ import annotations

from .common import Ctx, RateLimiter, save_from_url

SOURCE = "sec_edgar"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
# Richest annual disclosures; one per company for issuer diversity.
WANTED_FORMS = ("10-K", "20-F")


def fetch(ctx: Ctx, limit: int) -> int:
    # 2 requests/company at 0.2s apart => ~5 req/s, comfortably under SEC's cap.
    rate = RateLimiter(0.2)
    s = ctx.session()
    try:
        tickers = s.get(TICKERS_URL, timeout=60).json()
    except Exception as e:  # noqa: BLE001
        ctx.log(f"  ! could not load company list: {e}")
        return 0

    added = 0
    for company in tickers.values():
        if added >= limit:
            break
        cik = int(company["cik_str"])
        ticker = company.get("ticker", "")
        name = company.get("title", ticker)
        rate.wait()
        try:
            sub = s.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", timeout=60).json()
        except Exception as e:  # noqa: BLE001
            ctx.log(f"  ! submissions failed for {ticker}: {e}")
            continue

        recent = sub.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accs = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        dates = recent.get("filingDate", [])
        for i, form in enumerate(forms):
            if form not in WANTED_FORMS:
                continue
            doc = docs[i] if i < len(docs) else ""
            if not doc or not doc.lower().endswith((".htm", ".html")):
                continue
            acc = accs[i].replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
            title = f"{name} ({ticker}) {form} {dates[i]}"
            if save_from_url(
                ctx, SOURCE, url, title, s, rate,
                extra={"form": form, "cik": cik, "ticker": ticker, "filing_date": dates[i]},
            ):
                added += 1
            break  # only the most recent qualifying filing per company
    return added
