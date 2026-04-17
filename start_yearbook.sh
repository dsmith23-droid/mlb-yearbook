#!/bin/bash
cd "$(dirname "$0")"
echo "Starting MLB Yearbook..."
echo "Your browser will open automatically."
echo "Keep this terminal open while using the site."
echo "Press Ctrl+C to stop."
sleep 1
python3 -m http.server 8000 &
SERVER_PID=$!
sleep 1
# Open browser
if command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:8000
elif command -v open &>/dev/null; then
    open http://localhost:8000
fi
wait $SERVER_PID
