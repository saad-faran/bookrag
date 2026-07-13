"""Corporate annual reports / investor decks (heavily designed multimodal PDFs).

The single richest multimodal source here: charts, infographics, photography,
multi-column spreads -- the real test for a multimodal RAG pipeline.

Two paths:
  1. Seed file (downloaders/annual_reports_seed.txt) of direct PDF URLs (highest confidence).
  2. Two-hop scrape of annualreports.com: listing -> /Company/<slug> -> HostedData/*.pdf.

The scraper is defensive: any page that doesn't match degrades to zero results for
that company rather than crashing the run.
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import Ctx, RateLimiter, read_seed_file, save_from_url

SOURCE = "annual_reports"
SEED_FILE = Path(__file__).with_name("annual_reports_seed.txt")
BASE = "https://www.annualreports.com"
LISTING = BASE + "/Companies?a="
_COMPANY_RE = re.compile(r'href="(/Company/[^"]+)"')
_PDF_RE = re.compile(r'"(/HostedData/[^"]+\.pdf)"', re.IGNORECASE)


def fetch(ctx: Ctx, limit: int) -> int:
    rate = RateLimiter(1.5)  # polite: this is a scrape, not an API
    s = ctx.session()
    added = 0

    # Path 1: explicit seed URLs.
    for url, title in read_seed_file(SEED_FILE):
        if added >= limit:
            return added
        if save_from_url(ctx, SOURCE, url, title, s, rate):
            added += 1

    # Path 2: scrape the company directory.
    rate.wait()
    try:
        listing = s.get(LISTING, timeout=60).text
    except Exception as e:  # noqa: BLE001
        ctx.log(f"  ! company listing fetch failed: {e}")
        return added

    company_paths = list(dict.fromkeys(_COMPANY_RE.findall(listing)))  # de-dup, keep order
    for cpath in company_paths:
        if added >= limit:
            break
        rate.wait()
        try:
            page = s.get(BASE + cpath, timeout=60).text
        except Exception:  # noqa: BLE001
            continue
        pdfs = _PDF_RE.findall(page)
        if not pdfs:
            continue
        pdf_url = BASE + pdfs[0]  # newest report is listed first
        name = cpath.rsplit("/", 1)[-1].replace("-", " ").title()
        title = f"{name} Annual Report"
        if save_from_url(ctx, SOURCE, pdf_url, title, s, rate, extra={"company_path": cpath}):
            added += 1

    if added == 0:
        ctx.log(
            "  i annual_reports yielded 0. Add direct PDF URLs to "
            f"{SEED_FILE.name} to guarantee results."
        )
    return added
