"""Shared plumbing for every BookRAG corpus downloader.

Design goals (senior-SWE checklist):
  - Idempotent / resumable   -> a JSON manifest tracks every doc by URL + content hash.
  - Deduplicated             -> same URL or same bytes are never stored twice.
  - Polite                   -> per-source rate limiting, honest User-Agent with contact email.
  - Dependency-light         -> only `requests`; everything else is stdlib.

Each source module exposes:
    SOURCE = "<slug>"
    def fetch(ctx: Ctx, limit: int) -> int   # returns number of NEW docs saved
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

# SEC (and general etiquette) require a real contact address in the User-Agent.
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "royalekiller786@gmail.com")
USER_AGENT = f"BookRAG-corpus-builder/1.0 ({CONTACT_EMAIL})"


def slugify(text: str, maxlen: int = 80) -> str:
    text = re.sub(r"[^\w\s-]", "", (text or "")).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:maxlen].strip("-") or "doc"


class RateLimiter:
    """Blocks so that consecutive calls are at least `min_interval` seconds apart."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            delta = self.min_interval - (time.monotonic() - self._last)
            if delta > 0:
                time.sleep(delta)
            self._last = time.monotonic()


class Manifest:
    """Append-only record of everything downloaded, persisted to manifest.json."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.records: list[dict] = []
        self._urls: set[str] = set()
        self._hashes: set[str] = set()
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self.records = data.get("documents", [])
            for r in self.records:
                self._urls.add(r.get("url"))
                self._hashes.add(r.get("sha256"))

    def has_url(self, url: str) -> bool:
        return url in self._urls

    def has_hash(self, h: str) -> bool:
        return h in self._hashes

    def count_by_source(self, source: str) -> int:
        return sum(1 for r in self.records if r.get("source") == source)

    def total(self) -> int:
        return len(self.records)

    def add(self, rec: dict) -> None:
        self.records.append(rec)
        self._urls.add(rec.get("url"))
        self._hashes.add(rec.get("sha256"))
        self.save()

    def save(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"documents": self.records}, indent=2))
        tmp.replace(self.path)  # atomic; a crash mid-write never corrupts the manifest


@dataclass
class Ctx:
    out_dir: Path
    manifest: Manifest
    log: Callable[[str], None]

    def session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
        return s


def _guess_ext(url: str, content_type: str) -> str:
    stem = url.lower().split("?")[0]
    for e in (".pdf", ".htm", ".html", ".txt", ".epub"):
        if stem.endswith(e):
            return e
    ct = (content_type or "").lower()
    if "pdf" in ct:
        return ".pdf"
    if "html" in ct:
        return ".html"
    return ".pdf"


def save_from_url(
    ctx: Ctx,
    source: str,
    url: str,
    title: str,
    session: requests.Session,
    rate: RateLimiter,
    min_bytes: int = 2000,
    extra: Optional[dict] = None,
) -> Optional[dict]:
    """Download `url`, dedup by URL and by content hash, record it in the manifest.

    Returns the new manifest record, or None if skipped/failed.
    """
    if ctx.manifest.has_url(url):
        return None
    rate.wait()
    try:
        r = session.get(url, timeout=90)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001 - one bad doc must never kill the run
        ctx.log(f"  ! fetch failed: {e} <{url}>")
        return None

    data = r.content
    if len(data) < min_bytes:
        ctx.log(f"  ! too small ({len(data)}B), skipping: {title[:50]}")
        return None

    h = hashlib.sha256(data).hexdigest()
    if ctx.manifest.has_hash(h):
        ctx.log(f"  = duplicate content, skipping: {title[:50]}")
        return None

    ext = _guess_ext(url, r.headers.get("Content-Type", ""))
    dest_dir = ctx.out_dir / source
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{slugify(title)}-{h[:8]}{ext}"
    (dest_dir / fname).write_bytes(data)

    rec = {
        "source": source,
        "title": title.strip(),
        "url": url,
        "filename": f"{source}/{fname}",
        "sha256": h,
        "bytes": len(data),
        "content_type": r.headers.get("Content-Type", ""),
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if extra:
        rec.update(extra)
    ctx.manifest.add(rec)
    ctx.log(f"  + [{source}] {title[:60]}  ({len(data)//1024} KB)")
    return rec


def read_seed_file(path: Path) -> list[tuple[str, str]]:
    """Parse a seed file of `URL` or `URL | Title` lines. `#` starts a comment."""
    out: list[tuple[str, str]] = []
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            url, title = line.split("|", 1)
            out.append((url.strip(), title.strip()))
        else:
            out.append((line, line.rsplit("/", 1)[-1]))
    return out
