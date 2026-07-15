"""Central configuration for BookRAG. One place to tune everything.

Values can be overridden via environment variables (see .env.example).
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------- data sources
CORPUS_DIR = ROOT / "corpus"          # multimodal corpus (built by acquire.py)
BOOKS_DIR = ROOT / "books"            # the original 11 clean-text books
MANIFEST_PATH = ROOT / "manifest.json"
CHROMA_DIR = ROOT / "chroma_db"       # vector store + BM25 pickles (gitignore)
INGEST_STATE = CHROMA_DIR / "ingest_state.json"

COLLECTION_NAME = "bookrag"

# ------------------------------------------------------------------ parsing
MIN_CHARS_PER_PAGE = 40      # below this, a PDF page is treated as scanned -> OCR fallback
MIN_TABLE_CELLS = 6          # HTML/PDF tables smaller than this are treated as layout noise
ENABLE_OCR = os.getenv("BOOKRAG_OCR", "auto")      # "auto" | "on" | "off" — image/scan OCR
ENABLE_AUDIO = os.getenv("BOOKRAG_AUDIO", "auto")  # "auto" | "off" — audio transcription
WHISPER_MODEL = os.getenv("BOOKRAG_WHISPER_MODEL", "base")  # faster-whisper / whisper size

# ------------------------------------------------------------------ chunking
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TABLE_CHUNK_SIZE = 1600      # tables stay whole up to this size before row-splitting
# Cap chunks per document (evenly sampled if exceeded). Bounds SEC/report blow-up so
# the whole index fits in ~8 GB RAM and retrieval stays sharp. Raise if you have more RAM.
MAX_CHUNKS_PER_DOC = int(os.getenv("BOOKRAG_MAX_CHUNKS_PER_DOC", "250"))

# ------------------------------------------------------------------ embeddings
EMBED_MODEL = os.getenv("BOOKRAG_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_BATCH = 64
# "auto" uses the Apple-Silicon GPU (MPS) if available, else CPU. Override: cpu|mps|cuda.
EMBED_DEVICE = os.getenv("BOOKRAG_EMBED_DEVICE", "auto")

# ------------------------------------------------------------------ retrieval
N_DENSE = 15
N_SPARSE = 15
N_FINAL = int(os.getenv("BOOKRAG_N_FINAL", "5"))   # excerpts sent to the LLM (fewer = fewer tokens)
RRF_K = 60
# Cap chars per excerpt in the LLM prompt so a huge SEC table can't blow the token budget.
# Groq's free tier allows only ~6k tokens/MINUTE, and excerpts are sent to both the
# generator and the grounding evaluator — keep this lean or demos get rate-limited.
EXCERPT_CHARS = int(os.getenv("BOOKRAG_EXCERPT_CHARS", "450"))
# Cross-reference costs one extra (small) LLM call per grounded RAG turn. Set to 0 to
# trade the source-agreement check for lower latency / token use.
CROSS_REFERENCE = os.getenv("BOOKRAG_CROSS_REFERENCE", "1") == "1"

# ------------------------------------------------------------------ LLM (OpenAI-compatible)
# Any OpenAI-compatible endpoint works. Provider auto-selects: Groq if GROQ_API_KEY is
# set, else local Ollama. Set BOOKRAG_MOCK_LLM=1 to run the whole pipeline with a fast
# deterministic fake model (no network / no key) -- used for UI development & testing.
PROVIDER = os.getenv("BOOKRAG_PROVIDER", "groq" if os.getenv("GROQ_API_KEY") else "ollama").lower()
MOCK_LLM = os.getenv("BOOKRAG_MOCK_LLM", "0") == "1"

if PROVIDER == "groq":
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    LLM_API_KEY = os.getenv("GROQ_API_KEY", "")
    # Groq is very fast; a small model for routing, a strong one for generation/eval.
    MODEL_ROUTER = os.getenv("BOOKRAG_MODEL_ROUTER", "llama-3.1-8b-instant")
    MODEL_GENERAL = os.getenv("BOOKRAG_MODEL_GENERAL", "llama-3.1-8b-instant")
    # 8b-instant has a much larger free daily token budget than the 70B model and is
    # plenty for grounded RAG. Set BOOKRAG_MODEL_HEAVY=llama-3.3-70b-versatile in .env
    # for max quality (but mind the 100k tokens/day free cap).
    MODEL_HEAVY = os.getenv("BOOKRAG_MODEL_HEAVY", "llama-3.1-8b-instant")
else:
    LLM_BASE_URL = os.getenv("OLLAMA_BASE_URL", os.getenv("LLM_BASE_URL", "http://localhost:11434"))
    LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
    MODEL_ROUTER = os.getenv("BOOKRAG_MODEL_ROUTER", "qwen3.5:0.8b")
    MODEL_GENERAL = os.getenv("BOOKRAG_MODEL_GENERAL", "qwen3.5:2b")
    MODEL_HEAVY = os.getenv("BOOKRAG_MODEL_HEAVY", "qwen3.5:4b")

LLM_TIMEOUT = int(os.getenv("BOOKRAG_LLM_TIMEOUT", "120"))


def llm_base_url() -> str:
    """Normalise to an OpenAI-compatible /v1 base."""
    base = LLM_BASE_URL.rstrip("/")
    return base if base.endswith("/v1") else base + "/v1"
