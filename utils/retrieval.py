"""Hybrid retrieval: Chroma dense + BM25 sparse, fused with Reciprocal Rank Fusion.

retrieve() returns the top-N fused chunks with full provenance (title, source, page,
element_type) for citations. On a retry it merges the first attempt's docs into the
candidate pool before re-fusing -- cumulative context, never less.
"""
from __future__ import annotations

import hashlib
import pickle

import chromadb

import config
from utils.embeddings import BGEEmbeddings


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()


class RetrieverClient:
    def __init__(self) -> None:
        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        self.collection = client.get_collection(config.COLLECTION_NAME)
        self.embedder = BGEEmbeddings()
        self.bm25 = pickle.loads((config.CHROMA_DIR / "bm25.pkl").read_bytes())
        self.corpus = pickle.loads((config.CHROMA_DIR / "bm25_corpus.pkl").read_bytes())
        self.corpus_meta = pickle.loads((config.CHROMA_DIR / "corpus_metadata.pkl").read_bytes())

    # -------------------------------------------------- individual retrievers
    def _dense(self, query: str, n: int) -> list[dict]:
        emb = self.embedder.embed_query(query)
        res = self.collection.query(
            query_embeddings=[emb], n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        out = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            out.append({"text": doc, "meta": meta, "score": 1.0 - dist})
        return out

    def _sparse(self, query: str, n: int) -> list[dict]:
        scores = self.bm25.get_scores(query.lower().split())
        top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n]
        return [
            {"text": self.corpus[i], "meta": self.corpus_meta[i], "score": float(scores[i])}
            for i in top if scores[i] > 0
        ]

    # -------------------------------------------------- RRF fusion
    def _fuse(self, ranked_lists: list[list[dict]], n_final: int) -> list[dict]:
        agg: dict[str, dict] = {}
        for lst in ranked_lists:
            for rank, item in enumerate(lst, start=1):
                k = _key(item["text"])
                entry = agg.setdefault(k, {"item": item, "rrf": 0.0})
                entry["rrf"] += 1.0 / (config.RRF_K + rank)
        fused = sorted(agg.values(), key=lambda e: e["rrf"], reverse=True)[:n_final]
        results = []
        for e in fused:
            it, m = e["item"], e["item"]["meta"]
            results.append({
                "text": it["text"],
                "title": m.get("title", ""),
                "source": m.get("source", ""),
                "page": m.get("page", ""),
                "element_type": m.get("element_type", "text"),
                "rrf_score": round(e["rrf"], 5),
            })
        return results

    def retrieve(
        self,
        query: str,
        extra_docs: list[dict] | None = None,
        n_dense: int | None = None,
        n_sparse: int | None = None,
        n_final: int | None = None,
    ) -> list[dict]:
        n_dense = n_dense or config.N_DENSE
        n_sparse = n_sparse or config.N_SPARSE
        n_final = n_final or config.N_FINAL

        lists = [self._dense(query, n_dense), self._sparse(query, n_sparse)]
        if extra_docs:  # retry: fold prior docs in as another ranked list (dedup by fusion)
            lists.append([{"text": d["text"], "meta": d} for d in extra_docs])
        return self._fuse(lists, n_final)


# Backwards-compatible module-level helper matching the spec signature.
_client: RetrieverClient | None = None


def get_retriever() -> RetrieverClient:
    global _client
    if _client is None:
        _client = RetrieverClient()
    return _client


def retrieve_and_fuse(query: str, n_dense: int = config.N_DENSE,
                      n_sparse: int = config.N_SPARSE, n_final: int = config.N_FINAL) -> list[dict]:
    return get_retriever().retrieve(query, n_dense=n_dense, n_sparse=n_sparse, n_final=n_final)
