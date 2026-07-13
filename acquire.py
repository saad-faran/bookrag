#!/usr/bin/env python3
"""BookRAG corpus acquisition CLI.

Pulls a multimodal finance/business corpus from legal, API-driven sources into
./corpus/<source>/ and records everything in ./manifest.json. Idempotent and
resumable: rerun any time to top up toward the target.

Usage:
    python acquire.py                          # run all sources toward default quotas
    python acquire.py --only sec_edgar         # just one source
    python acquire.py --quota arxiv_qfin=60    # override a quota (repeatable)
    python acquire.py --target 200             # informational global cap
    python acquire.py --list                   # show current manifest tallies and exit

Set a contact email for SEC etiquette:  export CONTACT_EMAIL="you@example.com"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from downloaders import (
    annual_reports,
    arxiv_qfin,
    common,
    open_books,
    public_domain,
    sec_edgar,
    worldbank,
)

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "corpus"
MANIFEST_PATH = ROOT / "manifest.json"

# Ordered most-reliable-first so a short run still yields a strong corpus.
SOURCES = {
    "sec_edgar": sec_edgar,
    "worldbank": worldbank,
    "arxiv_qfin": arxiv_qfin,
    "public_domain": public_domain,
    "annual_reports": annual_reports,
    "open_books": open_books,
}

# Default per-source quotas (sum = 200).
DEFAULT_QUOTAS = {
    "sec_edgar": 80,
    "worldbank": 45,
    "arxiv_qfin": 35,
    "public_domain": 20,
    "annual_reports": 15,
    "open_books": 5,
}


def _log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Acquire a legal multimodal finance corpus for BookRAG.")
    p.add_argument("--only", choices=list(SOURCES), help="run a single source")
    p.add_argument("--quota", action="append", default=[], metavar="SOURCE=N",
                   help="override a source quota (repeatable)")
    p.add_argument("--target", type=int, default=200, help="informational global target")
    p.add_argument("--list", action="store_true", help="print current tallies and exit")
    args = p.parse_args()

    manifest = common.Manifest(MANIFEST_PATH)

    if args.list:
        _log(f"Corpus manifest: {manifest.total()} documents in {MANIFEST_PATH}")
        for name in SOURCES:
            _log(f"  {name:<16} {manifest.count_by_source(name)}")
        return 0

    quotas = dict(DEFAULT_QUOTAS)
    for override in args.quota:
        try:
            k, v = override.split("=")
            if k not in SOURCES:
                raise ValueError(k)
            quotas[k] = int(v)
        except ValueError:
            _log(f"Bad --quota '{override}' (use SOURCE=N with a known source)")
            return 2

    selected = [args.only] if args.only else list(SOURCES)
    OUT_DIR.mkdir(exist_ok=True)
    ctx = common.Ctx(out_dir=OUT_DIR, manifest=manifest, log=_log)

    _log(f"Starting acquisition -> {OUT_DIR}  (target ~{args.target}, contact={common.CONTACT_EMAIL})")
    _log(f"Already have {manifest.total()} docs.\n")

    grand_new = 0
    for name in selected:
        have = manifest.count_by_source(name)
        need = quotas[name] - have
        if need <= 0:
            _log(f"== {name}: quota met ({have}/{quotas[name]}), skipping ==")
            continue
        _log(f"== {name}: need {need} more (have {have}/{quotas[name]}) ==")
        try:
            new = SOURCES[name].fetch(ctx, need)
        except KeyboardInterrupt:
            _log("\nInterrupted -- manifest is saved; rerun to resume.")
            break
        except Exception as e:  # noqa: BLE001 - isolate source failures
            _log(f"  !! {name} crashed: {e} (continuing with next source)")
            new = 0
        grand_new += new
        _log(f"== {name}: +{new} this run (total {manifest.count_by_source(name)}/{quotas[name]}) ==\n")

    _log(f"Done. +{grand_new} new this run. Corpus now holds {manifest.total()} documents.")
    _log(f"Files: {OUT_DIR}/<source>/   Manifest: {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
