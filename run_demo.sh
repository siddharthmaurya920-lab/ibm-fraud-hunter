#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"   # always run from project root regardless of CWD

echo "📦 Installing dependencies..."
pip3 install -r requirements.txt

echo ""
echo "🏦 Generating multi-bank transactions..."
python3 src/data_generator.py

echo ""
echo "🔍 Running fraud detection inside secure vault..."
python3 src/fraud_detector.py

echo ""
echo "🚀 Starting server on http://localhost:5001 ..."
echo "   Press Ctrl+C to stop."
echo ""

# Open browser after a short delay (works on macOS and Linux)
(sleep 2 && (open http://localhost:5001 2>/dev/null || xdg-open http://localhost:5001 2>/dev/null || true)) &

python3 src/app.py
