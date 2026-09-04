#!/bin/bash

# ==========================================================
# CyberWatch: Cybersecurity Procurement Tracker Startup
# ==========================================================

echo "=========================================================="
echo "  🛡️  Starting CyberWatch Thailand Platform..."
echo "=========================================================="

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 1. Check Python Virtualenv
if [ ! -d "backend/venv" ]; then
    echo "📦 Setting up Python virtual environment..."
    python3 -m venv backend/venv
    backend/venv/bin/pip install --upgrade pip
    backend/venv/bin/pip install -r backend/requirements.txt
fi

# 2. Check Frontend Build
if [ ! -d "frontend/dist" ]; then
    echo "⚡ Building frontend production assets..."
    npm install --prefix frontend
    npm run build --prefix frontend
fi

# 3. Start Application
echo ""
echo "🚀 Application is starting on: http://localhost:8000"
echo "📖 REST API Documentation: http://localhost:8000/docs"
echo "Press Ctrl+C to stop the server."
echo "=========================================================="
echo ""

export PYTHONPATH=.
exec backend/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
