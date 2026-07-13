"""Structure-aware chunking.

Text elements are split with a recursive splitter (paragraph-first). Table elements
are kept whole when they fit, else split by rows with the header repeated on each
piece -- so a financial table never loses its column labels mid-split.

Every chunk carries flat, Chroma-safe metadata (str/int/float/bool only) including
provenance (source, title, page, element_type) used later for citations + filtering.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

import config
from utils.parsing import Element

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=config.CHUNK_SIZE,
    chunk_overlap=config.CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)


def _sanitize(meta: dict) -> dict:
    out = {}
    for k, v in meta.items():
        if v is None:
            out[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def _split_table(md: str) -> list[str]:
    """Split an oversized Markdown table by rows, repeating header lines."""
    lines = md.splitlines()
    if not lines:
        return []
    # Header = leading lines up to and including the '---' separator (0-2 lines).
    header, body_start = [], 0
    for i, ln in enumerate(lines):
        header.append(ln)
        if set(ln.replace("|", "").replace(" ", "")) <= {"-"} and "-" in ln:
            body_start = i + 1
            break
    body = lines[body_start:] or lines
    pieces, cur, cur_len = [], [], 0
    for row in body:
        if cur and cur_len + len(row) > config.TABLE_CHUNK_SIZE:
            pieces.append("\n".join(header + cur))
            cur, cur_len = [], 0
        cur.append(row)
        cur_len += len(row) + 1
    if cur:
        pieces.append("\n".join(header + cur))
    return pieces


def chunk_elements(elements: list[Element], doc_meta: dict) -> list[Chunk]:
    chunks: list[Chunk] = []
    for el in elements:
        base = dict(doc_meta)
        base["page"] = el.page if el.page is not None else ""
        base["element_type"] = el.element_type

        if el.element_type == "table":
            page_tag = f" (p.{el.page})" if el.page else ""
            provenance = f"Table from {doc_meta.get('title', 'document')}{page_tag}:\n"
            pieces = [el.text] if len(el.text) <= config.TABLE_CHUNK_SIZE else _split_table(el.text)
            for piece in pieces:
                chunks.append(Chunk(text=provenance + piece, metadata=_sanitize(base)))
        else:
            for piece in _splitter.split_text(el.text):
                piece = piece.strip()
                if len(piece) < 30:  # drop stray fragments
                    continue
                chunks.append(Chunk(text=piece, metadata=_sanitize(base)))
    return chunks
