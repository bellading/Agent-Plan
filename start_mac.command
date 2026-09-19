#!/bin/bash
# Double-click this file on macOS to start AgentPlan (web page + reminder scheduler).
cd "$(dirname "$0")"

echo "Setting up database (first run only)..."
python3 db/init_db.py

echo "Starting reminder scheduler..."
python3 scheduler.py &
SCHEDULER_PID=$!

echo "Starting web page..."
python3 app.py &
APP_PID=$!

sleep 1.5
open "http://127.0.0.1:5000"

echo ""
echo "AgentPlan is running. Close this window (or press Ctrl+C) to stop both."
trap "kill $SCHEDULER_PID $APP_PID 2>/dev/null" EXIT
wait
