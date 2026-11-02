@echo off
REM Double-click this file on Windows to start AgentPlan (web page + reminder scheduler).
cd /d "%~dp0"

echo Setting up database (first run only)...
python db\init_db.py

echo Starting reminder scheduler (minimized)...
start /min "AgentPlan Scheduler" cmd /k python scheduler.py

echo Starting web page (minimized)...
start /min "AgentPlan Web" cmd /k python app.py

timeout /t 2 >nul
start http://127.0.0.1:5000

exit
