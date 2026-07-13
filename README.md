<div align="center">

# 📚 BookRAG

### Agentic, grounded Retrieval-Augmented Generation over a multimodal finance corpus

**Ask questions about SEC filings, annual reports, economic papers and finance books — and watch the RAG pipeline execute live, node by node, with sources and a strict anti-hallucination gate.**

![status](https://img.shields.io/badge/status-working-brightgreen)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![next.js](https://img.shields.io/badge/frontend-Next.js%2015-black)
![llm](https://img.shields.io/badge/LLM-Groq%20(free)-orange)
![license](https://img.shields.io/badge/license-MIT-lightgrey)

</div>

---

## Table of contents
1. [What is BookRAG?](#what-is-bookrag)
2. [Key features](#key-features)
3. [Architecture](#architecture)
4. [Tech stack](#tech-stack)
5. [Quickstart](#quickstart) — get running in ~15 minutes
6. [How the pipeline works](#how-the-pipeline-works)
7. [Configuration](#configuration)
8. [Project structure](#project-structure)
9. [Data sources (all legal)](#data-sources-all-legal)
10. [Troubleshooting](#troubleshooting)
11. [Roadmap](#roadmap)

---

## What is BookRAG?

BookRAG is an end-to-end, **quality-first** RAG system. Its guiding principle is **zero hallucination**: every answer must be grounded in retrieved source excerpts, verified by a strict fact-checking step, and cited. If it can't verify an answer, it says so honestly instead of guessing.

It's built around a **genuinely multimodal** corpus — not just clean text, but SEC filings full of financial **tables**, glossy annual-report PDFs, scanned public-domain documents, and quantitative-finance papers — acquired automatically from free, legal, API-driven sources.

The frontend turns the usually-invisible RAG pipeline into a **live, interactive visualization**: as you ask a question, you watch each stage (rewrite → retrieve → generate → verify → retry) light up in real time, with per-node timings and a trace you can click through — so a developer, reviewer, or team lead can understand *exactly* what the system is doing without reading logs.

> **New to RAG?** RAG = "Retrieval-Augmented Generation": instead of asking a language model to answer from memory (which hallucinates), you first **retrieve** relevant passages from your own documents, then ask the model to answer **using only those passages**. BookRAG adds retrieval fusion, a grounding check, and an automatic retry on top of that.

---

## Key features

- **🧠 Agentic pipeline** (LangGraph) — query rewriting + routing, hybrid retrieval, grounded generation, a strict grounding gate, and one automatic query-expansion **retry** when an answer can't be verified.
- **🔀 Hybrid retrieval** — dense vector search (Chroma) **+** sparse keyword search (BM25), fused with **Reciprocal Rank Fusion**.
- **📊 Multimodal ingestion** — extracts narrative text, **financial tables → Markdown**, and OCRs scanned pages, from PDFs *and* HTML SEC filings.
- **📡 Live pipeline UI** — a three-panel Next.js app: an interactive flowchart that executes in real time, a streamed answer with source cards + grounding badge, and a trace timeline with per-node durations.
- **💾 Persistent, context-aware chats** — new/saved/resumable conversations, a rolling per-chat summary, and a **cross-chat user profile** that adapts over time.
- **🆓 Runs free, no GPU** — Groq's free cloud LLM for generation; local CPU/Apple-Silicon (MPS) embeddings.
- **⚖️ Legally clean corpus** — every source is public-domain, open, or government data (see [Data sources](#data-sources-all-legal)).

---

## Architecture

```
                        ┌──────────────── acquire.py ─────────────────┐
   1. Acquisition       │  SEC EDGAR · World Bank · arXiv q-fin ·       │  ──▶  corpus/ + manifest.json
   (legal, API-driven)  │  annualreports.com · Internet Archive        │
                        └──────────────────────────────────────────────┘
                                            │
                        ┌──────────────── ingest.py ───────────────────┐
   2. Multimodal        │  parse (PDF text + tables + OCR / HTML→tables)│  ──▶  chroma_db/
      ingestion         │  → structure-aware chunk → BGE embed          │       (vectors + BM25)
                        │  → Chroma (dense) + BM25 (sparse)             │
                        └──────────────────────────────────────────────┘
                                            │
   3. Query time    ┌──────── FastAPI backend (server/) ───────┐   SSE   ┌──── Next.js UI (webnext/) ────┐
                    │  LangGraph pipeline + SQLite chats +      │ ◀─────▶ │  live flowchart · streamed    │
                    │  user-memory snapshots. Streams every     │ events  │  answer · trace timeline      │
                    │  node's start/end + timing + tokens.      │         │                               │
                    └───────────────────────────────────────────┘         └───────────────────────────────┘
```

**The LangGraph pipeline:**

```
START → rewrite_and_route
        ├─ "general" → general_answer ─────────────┐
        └─ "rag" → retrieve → generate → evaluate_grounding
                     ▲                        │
                     │        grounded? ──────┤
                     │            yes ───────▶ build_final_answer → END
                     └── expand_query ◀── no (first attempt only)
```

---

## Tech stack

| Layer | Technology |
|---|---|
| **Orchestration** | LangGraph (agentic state machine) |
| **LLM** | Groq (`llama-3.1-8b-instant`) via an OpenAI-compatible API — swappable to any provider |
| **Embeddings** | `BAAI/bge-small-en-v1.5` (local, CPU or Apple-Silicon MPS) |
| **Vector store** | ChromaDB (dense, cosine) |
| **Sparse search** | `rank-bm25` (BM25Okapi) + Reciprocal Rank Fusion |
| **Parsing** | PyMuPDF, pdfplumber, BeautifulSoup + pandas (tables) |
| **Backend** | FastAPI + SSE (Server-Sent Events), SQLite |
| **Frontend** | Next.js 15 (App Router), React Flow, Tailwind CSS v4, Framer Motion |

---

## Quickstart

### Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- A free **Groq API key** → [console.groq.com/keys](https://console.groq.com/keys) (no card, no GPU)
- ~2 GB free disk for the corpus + index

### 1 — Install
```bash
git clone https://github.com/saad-faran/bookrag.git
cd bookrag
./setup.sh            # creates .venv, installs Python + frontend deps
```

### 2 — Add your Groq key
```bash
cp .env.example .env
# edit .env → set GROQ_API_KEY=gsk_...   (and keep BOOKRAG_MOCK_LLM=0)
```

### 3 — Build the corpus + index (one-time)
```bash
. .venv/bin/activate
export CONTACT_EMAIL="you@example.com"      # required by SEC's usage policy

python acquire.py            # downloads ~200 legal, multimodal finance docs  → corpus/
python ingest.py             # parse → chunk → embed → index                  → chroma_db/
```
> First run downloads the embedding model (~130 MB). Ingestion is CPU-bound; see [Troubleshooting](#troubleshooting) if you have ≤8 GB RAM.

### 4 — Run
```bash
./run.sh                     # backend :8000  +  frontend :5200
```
Open **http://localhost:5200** and ask a question.

### Want to try the UI *without* a key or corpus?
```bash
BOOKRAG_MOCK_LLM=1 ./run.sh  # deterministic fake answers; the whole UI/pipeline still runs
```

---

## How the pipeline works

Each node is a step in the LangGraph state machine (`pipeline.py`). The UI names and describes each one live.

| Node | Model | What it does |
|---|---|---|
| **rewrite_and_route** | router | Rewrites the query to be search-friendly and decides: conversational (`general`) or knowledge-base (`rag`). |
| **retrieve** | — | Dense (Chroma) + sparse (BM25) search, fused via RRF. On retry, merges the first attempt's docs for cumulative context. |
| **generate** | heavy | Answers using **only** the excerpts (text + Markdown tables), citing sources, adapting length to the question. |
| **evaluate_grounding** | heavy | A strict fact-checker: is every claim traceable to an excerpt? If not → reject. |
| **expand_query** | router | On a grounding failure (once), expands the query with related terms and retries retrieval. |
| **general_answer** | general | Handles small talk / out-of-scope with a gentle nudge back to the finance domain. |
| **build_final_answer** | — | Assembles the answer + source citations + a disclaimer if it couldn't be verified. |

---

## Configuration

All configuration lives in `config.py` and can be overridden via environment variables (`.env`). The most useful:

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | — | Your free Groq key. If set, provider auto-selects Groq. |
| `BOOKRAG_MODEL_HEAVY` | `llama-3.1-8b-instant` | Generation + grounding model. Use `llama-3.3-70b-versatile` for higher quality (mind the free daily token cap). |
| `BOOKRAG_MOCK_LLM` | `0` | `1` = run the whole pipeline with a fake model (no key needed). |
| `BOOKRAG_N_FINAL` | `5` | Excerpts sent to the LLM (higher = richer answers, more tokens). |
| `BOOKRAG_MAX_CHUNKS_PER_DOC` | `250` | Caps chunks per document (bounds RAM/index size). Raise if you have more RAM. |
| `BOOKRAG_EMBED_DEVICE` | `auto` | `auto` uses Apple-Silicon GPU (MPS) if available, else CPU. |
| `OLLAMA_BASE_URL` | — | Point at a local Ollama instead of Groq (unlimited, slower, no key). |

---

## Project structure

```
bookrag/
├── acquire.py            # corpus acquisition CLI          → see ACQUIRING.md
├── ingest.py             # multimodal ingestion pipeline
├── pipeline.py           # LangGraph agentic RAG pipeline
├── config.py             # central configuration
├── app.py                # optional lightweight Streamlit UI
├── run.sh / setup.sh     # one-command run / setup
├── downloaders/          # one module per data source
├── utils/                # parsing, chunking, embeddings, retrieval, history, llm
├── server/               # FastAPI backend: SSE streaming, SQLite chats, memory
└── webnext/              # Next.js frontend (the live 3-panel UI)
```

---

## Data sources (all legal)

BookRAG acquires only free/open/public data, so the project is **redistributable and portfolio-safe**:

| Source | Content | Format |
|---|---|---|
| **SEC EDGAR** | 10-K / 20-F annual filings | HTML (dense tables) |
| **World Bank** | Open economic reports | PDF |
| **arXiv q-fin** | Quant-finance / economics papers | PDF |
| **Internet Archive** | Public-domain finance texts | scanned PDF |
| **annualreports.com** | Corporate annual reports | PDF |

> The `books/` directory (personal-finance books) is **not** included in this repository for copyright reasons — the pipeline works entirely on the legal sources above. See `ACQUIRING.md` for details.

---

## Troubleshooting

**Ingestion is slow / freezes on a machine with ≤8 GB RAM.**
The full corpus is ~40k chunks. Holding everything in memory can trigger swap-thrashing on 8 GB. It's already capped at 250 chunks/doc; lower `BOOKRAG_MAX_CHUNKS_PER_DOC` further, or ingest a subset with `python ingest.py --source sec_edgar` / `--limit 50`.

**Groq `429 rate_limit_exceeded`.**
You've hit the free daily token cap. The default `llama-3.1-8b-instant` has a large budget; if you switched to the 70B model, switch back, or lower `BOOKRAG_N_FINAL`. It resets daily. Alternatively use a local Ollama (`OLLAMA_BASE_URL`).

**The flowchart / corpus stats are empty right after launch.**
The backend loads the index + embedding model on startup (~10–20 s). The UI retries automatically and fills in once it's ready.

**`ModuleNotFoundError` when running scripts.**
Activate the venv first: `. .venv/bin/activate` (or run via `./run.sh`, which uses it automatically).

---

## Roadmap

- [ ] Deployed public demo (Vercel + a hosted backend)
- [ ] Approximate / quantized index for faster retrieval at scale
- [ ] Better SEC table normalization (layout-aware parsing, e.g. `docling`)
- [ ] Per-token LLM streaming (currently node-level streaming + typed answer)
- [ ] Evaluation harness (retrieval hit-rate + grounding accuracy)

---

<div align="center">
Built as an end-to-end demonstration of production-minded, grounded RAG.<br/>
See <a href="./BookRAG_Technical_Documentation.pdf">BookRAG_Technical_Documentation.pdf</a> for the full technical deep-dive.
</div>
