"""Legally usable full-length books (open-license textbooks + YOUR rights-cleared PDFs).

This is the deliberate, lawful replacement for "scrape more commercial ebooks."
It downloads ONLY from a seed file you control:
    downloaders/open_books_seed.txt   (one `URL` or `URL | Title` per line)

Put here:
  - Open-license textbooks you find (OpenStax, Saylor, Bookboon-free, CORE econ, etc.)
  - Any book PDF you personally hold distribution/usage rights to.

Nothing copyrighted is fetched automatically -- that keeps the corpus sellable and
CV-safe. See open_books_seed.txt for ready-to-uncomment examples.
"""
from __future__ import annotations

from pathlib import Path

from .common import Ctx, RateLimiter, read_seed_file, save_from_url

SOURCE = "open_books"
SEED_FILE = Path(__file__).with_name("open_books_seed.txt")


def fetch(ctx: Ctx, limit: int) -> int:
    rate = RateLimiter(1.0)
    s = ctx.session()
    added = 0
    seeds = read_seed_file(SEED_FILE)
    if not seeds:
        ctx.log(f"  i open_books: no seeds in {SEED_FILE.name} (skipping). Add open-license PDF URLs there.")
        return 0
    for url, title in seeds:
        if added >= limit:
            break
        if save_from_url(ctx, SOURCE, url, title, s, rate):
            added += 1
    return added
