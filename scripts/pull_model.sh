#!/bin/bash
# Pull Gemma model into Ollama — run after `docker compose up ollama`
set -e

OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
MODEL="${GEMMA_MODEL:-gemma3:27b}"

echo "🦙 Pulling $MODEL from Ollama at $OLLAMA_URL …"
echo "   (This may take 10–20 minutes for a 27B model)"

curl -sf "$OLLAMA_URL/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$MODEL\", \"stream\": false}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ Status:', d.get('status','unknown'))"

echo "✅ Model $MODEL ready!"
echo "   Test: curl $OLLAMA_URL/api/generate -d '{\"model\":\"$MODEL\",\"prompt\":\"Hello\",\"stream\":false}'"
