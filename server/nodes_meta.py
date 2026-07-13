"""Static metadata for every pipeline node — powers the UI flowchart, the node
dialogue box, and the trace panel. Order here defines the canonical top-to-bottom
layout on the frontend.
"""

NODES = [
    {
        "id": "rewrite_and_route",
        "label": "Rewrite & Route",
        "icon": "compass",
        "model": "router",
        "short": "Understands the question",
        "desc": "A lightweight model rewrites your question to be search-friendly and decides "
                "whether it needs the knowledge base (RAG) or a quick conversational reply.",
    },
    {
        "id": "retrieve",
        "label": "Hybrid Retrieve",
        "icon": "search",
        "model": "—",
        "short": "Finds the evidence",
        "desc": "Runs dense vector search (Chroma) and sparse keyword search (BM25) in parallel, "
                "then fuses both rankings with Reciprocal Rank Fusion to pick the best excerpts.",
    },
    {
        "id": "generate",
        "label": "Generate",
        "icon": "pen",
        "model": "heavy",
        "short": "Writes a grounded answer",
        "desc": "The main model answers using ONLY the retrieved excerpts (text + financial tables), "
                "citing sources and adapting length to the question.",
    },
    {
        "id": "evaluate_grounding",
        "label": "Grounding Gate",
        "icon": "shield",
        "model": "heavy",
        "short": "Fact-checks every claim",
        "desc": "A strict fact-checker verifies that each claim traces back to a source excerpt. "
                "If anything is unsupported, the answer is rejected and retried.",
    },
    {
        "id": "expand_query",
        "label": "Expand & Retry",
        "icon": "refresh",
        "model": "router",
        "short": "Broadens the search",
        "desc": "On a grounding failure, the query is expanded with related financial concepts and "
                "the retrieval is retried once with cumulative context.",
    },
    {
        "id": "general_answer",
        "label": "General Answer",
        "icon": "chat",
        "model": "general",
        "short": "Handles small talk",
        "desc": "Conversational and out-of-scope questions are answered directly, with a gentle nudge "
                "back toward the finance/wealth domain.",
    },
    {
        "id": "build_final_answer",
        "label": "Finalize",
        "icon": "package",
        "model": "—",
        "short": "Assembles the response",
        "desc": "Packages the final answer with its source citations and a disclaimer if the answer "
                "could not be fully verified.",
    },
]

NODE_BY_ID = {n["id"]: n for n in NODES}
