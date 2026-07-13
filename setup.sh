#!/bin/bash
# One-command setup for BookRAG: Python venv + deps + frontend deps.
# Usage:  ./setup.sh
set -e
cd "$(dirname "$0")"

echo "▶ Creating Python virtual environment (.venv)…"
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate

echo "▶ Installing Python dependencies…"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt

echo "▶ Installing frontend dependencies (webnext)…"
( cd webnext && npm install --legacy-peer-deps )

echo ""
echo "✅ Setup complete."
echo ""
echo "Next steps:"
echo "  1. cp .env.example .env   &&   add your free Groq key (https://console.groq.com/keys)"
echo "  2. Build the corpus + index (one-time):"
echo "        . .venv/bin/activate"
echo "        export CONTACT_EMAIL=you@example.com"
echo "        python acquire.py        # download ~200 legal, multimodal finance docs"
echo "        python ingest.py         # parse -> chunk -> embed -> index"
echo "  3. ./run.sh                    # start backend :8000 + UI :5200"
