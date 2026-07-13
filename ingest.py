#!/usr/bin/env python3
"""BookRAG multimodal ingestion: corpus -> Chroma (dense) + BM25 (sparse).

Pipeline per document:  parse (text/tables/OCR)  ->  structure-aware chunk  ->
BGE passage embeddings  ->  Chroma vector store + BM25 index.

Usage:
    python ingest.py                       # full corpus + books/
    python ingest.py --sample              # ~2 docs/source (fast smoke test)
    python ingest.py --source sec_edgar    # one source only
    python ingest.py --limit 20            # cap total docs
    python ingest.py --max-pages 15        # cap pages/PDF (fast test of big docs)

Reads corpus metadata from manifest.json; also ingests the original books/*.pdf.
Idempotent: the collection is dropped and rebuilt each run.
"""
from __future__ import annotations

import argparse
import json
import pickle
import re
import time
from collections import Counter
from pathlib import Path

import chromadb

import config
from utils.chunking import chunk_elements
from utils.embeddings import BGEEmbeddings
from utils import parsing


# --------------------------------------------------------------- doc discovery
def _clean_title(name: str) -> str:
    stem = re.sub(r"-[0-9a-f]{8}$", "", Path(name).stem)  # strip our hash suffix
    return re.sub(r"[\s_-]+", " ", stem).strip().title()


def discover_docs(source_filter: str | None) -> list[dict]:
    """Return [{path, meta}] for every ingestable document."""
    docs: list[dict] = []

    if config.MANIFEST_PATH.exists():
        manifest = json.loads(config.MANIFEST_PATH.read_text()).get("documents", [])
        for rec in manifest:
            src = rec.get("source", "corpus")
            if source_filter and src != source_filter:
                continue
            path = config.CORPUS_DIR / rec["filename"]
            if not path.exists():
                continue
            docs.append({
                "path": path,
                "meta": {
                    "source": src,
                    "doc_id": rec["filename"],
                    "title": rec.get("title") or _clean_title(rec["filename"]),
                    "doc_type": src,
                    "url": rec.get("url", ""),
                    "ticker": rec.get("ticker", ""),
                    "form": rec.get("form", ""),
                },
            })

    if (not source_filter or source_filter == "books") and config.BOOKS_DIR.exists():
        for pdf in sorted(config.BOOKS_DIR.glob("*.pdf")):
            docs.append({
                "path": pdf,
                "meta": {
                    "source": "books", "doc_id": f"books/{pdf.name}",
                    "title": _clean_title(pdf.name), "doc_type": "book",
                    "url": "", "ticker": "", "form": "",
                },
            })
    return docs


# --------------------------------------------------------------- main
def main() -> int:
    p = argparse.ArgumentParser(description="Ingest the BookRAG multimodal corpus.")
    p.add_argument("--sample", action="store_true", help="~2 docs per source (smoke test)")
    p.add_argument("--source", help="ingest a single source (e.g. sec_edgar, books)")
    p.add_argument("--limit", type=int, help="cap total documents")
    p.add_argument("--max-pages", type=int, help="cap pages per PDF (fast testing)")
    args = p.parse_args()

    if args.max_pages:
        parsing.MAX_PAGES = args.max_pages  # honoured by parse_pdf

    docs = discover_docs(args.source)
    if args.sample:
        seen: Counter = Counter()
        picked = []
        for d in docs:
            s = d["meta"]["source"]
            if seen[s] < 2:
                picked.append(d)
                seen[s] += 1
        docs = picked
    if args.limit:
        docs = docs[: args.limit]

    if not docs:
        print("No documents found. Run acquire.py first, or check --source.")
        return 1

    print(f"Ingesting {len(docs)} documents. OCR engine: {'yes' if parsing.ocr_available() else 'no (text-layer only)'}")
    config.CHROMA_DIR.mkdir(exist_ok=True)

    t0 = time.time()
    all_chunks = []
    per_source = Counter()
    table_chunks = 0

    for i, d in enumerate(docs, 1):
        try:
            elements = parsing.parse_document(d["path"])
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(docs)}] ! parse failed {d['path'].name}: {e}")
            continue
        chunks = chunk_elements(elements, d["meta"])
        # Cap per-doc chunks (evenly sampled) so a few huge SEC filings don't blow up
        # RAM / index size. Keeps whole-document coverage via striding.
        cap = config.MAX_CHUNKS_PER_DOC
        if len(chunks) > cap:
            step = len(chunks) / cap
            chunks = [chunks[int(k * step)] for k in range(cap)]
        for c in chunks:
            c.metadata["chunk_id"] = len(all_chunks)
            all_chunks.append(c)
            per_source[d["meta"]["source"]] += 1
            if c.metadata.get("element_type") == "table":
                table_chunks += 1
        print(f"  [{i}/{len(docs)}] {d['meta']['source']:14} {d['meta']['title'][:44]:44} "
              f"-> {len(chunks):4} chunks")

    if not all_chunks:
        print("No chunks produced.")
        return 1

    print(f"\nTotal chunks: {len(all_chunks):,}  ({table_chunks:,} table chunks). Embedding...")

    # ---- Chroma (dense) ----
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    try:
        client.delete_collection(config.COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        config.COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )
    embedder = BGEEmbeddings()

    BATCH = 512
    texts = [c.text for c in all_chunks]
    metas = [c.metadata for c in all_chunks]
    all_chunks.clear()   # free the Chunk wrappers before the memory-heavy embed/index phase
    import gc; gc.collect()
    for start in range(0, len(texts), BATCH):
        batch_texts = texts[start:start + BATCH]
        embs = embedder.embed_passages(batch_texts)
        collection.add(
            ids=[f"c{j}" for j in range(start, start + len(batch_texts))],
            embeddings=embs,
            documents=batch_texts,
            metadatas=metas[start:start + len(batch_texts)],
        )
        print(f"    embedded {min(start + BATCH, len(texts)):,}/{len(texts):,}")

    # ---- BM25 (sparse) ----
    print("Building BM25 index...")
    from rank_bm25 import BM25Okapi

    tokenized = [t.lower().split() for t in texts]
    bm25 = BM25Okapi(tokenized)
    (config.CHROMA_DIR / "bm25.pkl").write_bytes(pickle.dumps(bm25))
    (config.CHROMA_DIR / "bm25_corpus.pkl").write_bytes(pickle.dumps(texts))
    (config.CHROMA_DIR / "corpus_metadata.pkl").write_bytes(pickle.dumps(metas))

    dt = time.time() - t0
    n_chunks = len(texts)
    state = {
        "documents": len(docs),
        "chunks": n_chunks,
        "table_chunks": table_chunks,
        "by_source": dict(per_source),
        "seconds": round(dt, 1),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    config.INGEST_STATE.write_text(json.dumps(state, indent=2))

    print(f"\nDone in {dt:.1f}s. {len(docs)} docs -> {n_chunks:,} chunks "
          f"({table_chunks:,} tables).")
    print("By source:", dict(per_source))
    print(f"Vector store: {config.CHROMA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
