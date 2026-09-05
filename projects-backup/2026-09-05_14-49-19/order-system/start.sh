#!/bin/bash
# Order System — Startup Script
# Usage: bash start.sh

set -e
cd "$(dirname "$0")/backend"

echo "🚀 Starting Order System Backend..."
echo "   API:  http://localhost:8000"
echo "   Docs: http://localhost:8000/docs"
echo "   Frontend: http://localhost:8000/static/index.html"
echo "   Admin: http://localhost:8000/admin/index.html"
echo ""

exec python -m uvicorn api:app --host 0.0.0.0 --port 8000
