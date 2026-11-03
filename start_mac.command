#!/bin/bash
# Double-click this file on macOS to start AgentPlan (web page + reminder
# scheduler, which runs as a background thread inside app.py -- no separate
# process to start for it).
cd "$(dirname "$0")"

echo "Setting up database (first run only)..."
python3 db/init_db.py

echo "Starting web page..."
python3 app.py &
APP_PID=$!

sleep 1.5
open "http://127.0.0.1:5000"

echo ""
echo "AgentPlan is running. Close this window (or press Ctrl+C) to stop it."
trap "kill $APP_PID 2>/dev/null" EXIT
wait
