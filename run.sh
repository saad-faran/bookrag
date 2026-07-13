#!/bin/bash
# Start BookRAG: FastAPI backend (:8000) + Next.js frontend (:5200).
# Usage:  ./run.sh          (uses .env — Groq if GROQ_API_KEY set)
#         BOOKRAG_MOCK_LLM=1 ./run.sh   (no key, mock answers)
set -e
cd "$(dirname "$0")"

# Load .env into this shell so the backend picks up GROQ_API_KEY etc.
[ -f .env ] && set -a && . ./.env && set +a

# Pick the interpreter with the deps: the project venv first, then $PY, then python3.
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python";
elif [ -n "$PY" ] && [ -x "$PY" ]; then :;
else PY=python3; fi

echo "▶ Starting backend on http://127.0.0.1:8000  (provider: ${GROQ_API_KEY:+groq}${GROQ_API_KEY:-ollama}, mock=${BOOKRAG_MOCK_LLM:-0})"
"$PY" -m uvicorn server.app:app --host 127.0.0.1 --port 8000 &
BACK=$!

echo "▶ Starting frontend on http://localhost:5200"
( cd webnext && npm run dev ) &
FRONT=$!

trap "echo; echo 'Stopping…'; kill $BACK $FRONT 2>/dev/null" EXIT INT TERM
echo "✅ Open http://localhost:5200  (Ctrl+C to stop)"
wait
