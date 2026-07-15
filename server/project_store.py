"""Per-project document vectors — a Chroma collection filtered by project_id.

Uploaded files are parsed (PDF/HTML/image-OCR/audio-transcribe/docx/csv), chunked, BGE-
embedded, and stored with rich metadata so answers can cite them (filename + page) and
the citation can open the original file. Multi-tenant isolation is by project_id in the
metadata `where` filter.

(In the docker/Postgres deployment these would live in pgvector; Chroma is used here so
the whole flow is verifiable without a running Postgres.)
"""
from __future__ import annotations

from pathlib import Path

import chromadb

import config
from utils.chunking import chunk_elements
from utils.embeddings import BGEEmbeddings
from utils.parsing import parse_document

COLLECTION = "project_docs"
_client = None
_collection = None
_embedder: BGEEmbeddings | None = None


def _coll():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        _collection = _client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"})
    return _collection


def _emb() -> BGEEmbeddings:
    global _embedder
    if _embedder is None:
        _embedder = BGEEmbeddings()
    return _embedder


def ingest_file(project_id: str, doc_id: str, filename: str, path: str) -> int:
    """Parse + chunk + embed an uploaded file into the project collection. Returns chunk count."""
    elements = parse_document(Path(path))
    doc_meta = {"source": "project", "project_id": project_id, "doc_id": doc_id,
                "title": filename, "doc_type": "upload", "filename": filename}
    chunks = chunk_elements(elements, doc_meta)
    if not chunks:
        return 0
    cap = config.MAX_CHUNKS_PER_DOC
    if len(chunks) > cap:
        step = len(chunks) / cap
        chunks = [chunks[int(k * step)] for k in range(cap)]

    texts = [c.text for c in chunks]
    metas = []
    for i, c in enumerate(chunks):
        m = dict(c.metadata)
        m["chunk_id"] = i
        metas.append(m)
    embs = _emb().embed_passages(texts)
    _coll().add(ids=[f"{doc_id}-{i}" for i in range(len(texts))],
                embeddings=embs, documents=texts, metadatas=metas)
    return len(texts)


def retrieve(project_id: str, query: str, n: int = 6) -> list[dict]:
    """Return top-n project chunks for a query, scoped to the project (with citation info)."""
    try:
        coll = _coll()
        if coll.count() == 0:
            return []
        emb = _emb().embed_query(query)
        res = coll.query(query_embeddings=[emb], n_results=n,
                         where={"project_id": project_id},
                         include=["documents", "metadatas", "distances"])
        out = []
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            out.append({
                "text": doc,
                "title": meta.get("filename", meta.get("title", "document")),
                "source": "project",
                "doc_id": meta.get("doc_id", ""),
                "project_id": project_id,
                "page": meta.get("page", ""),
                "element_type": meta.get("element_type", "text"),
                "rrf_score": round(1.0 - dist, 4),
            })
        return out
    except Exception as e:
        import traceback
        print(f"[project_store.retrieve failed] project_id={project_id}, query={query}: {e}")
        traceback.print_exc()
        return []


def delete_file(doc_id: str) -> None:
    try:
        _coll().delete(where={"doc_id": doc_id})
    except Exception:
        pass


def delete_project(project_id: str) -> None:
    try:
        _coll().delete(where={"project_id": project_id})
    except Exception:
        pass
