"""BGE embedding wrapper.

BGE models are asymmetric: queries get a prefix, passages do not. Getting this wrong
is the #1 cause of poor retrieval, so the two paths are explicit methods.
"""
from __future__ import annotations

from sentence_transformers import SentenceTransformer

import config

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model: SentenceTransformer | None = None


def _resolve_device() -> str:
    dev = config.EMBED_DEVICE
    if dev != "auto":
        return dev
    try:
        import torch
        if torch.backends.mps.is_available():   # Apple-Silicon GPU
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBED_MODEL, device=_resolve_device())
    return _model


class BGEEmbeddings:
    """Implements the chromadb EmbeddingFunction interface (passage embeddings)."""

    def __init__(self) -> None:
        self.model = _get_model()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(
            texts, normalize_embeddings=True, batch_size=config.EMBED_BATCH,
            show_progress_bar=False,
        ).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode(
            QUERY_PREFIX + text, normalize_embeddings=True
        ).tolist()

    # chromadb EmbeddingFunction interface
    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self.embed_passages(input)

    @staticmethod
    def name() -> str:  # chromadb >=0.5 expects EmbeddingFunctions to expose a name
        return "bge-small-en-v1.5"
