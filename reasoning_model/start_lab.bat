@echo off
rem Triage Lab: run the rule-based triage on sample data and see every reading and reason. Close this window to stop.
cd /d "%~dp0"
start "" http://localhost:8503
".venv\Scripts\python.exe" -m streamlit run src\triage\lab_app.py --server.port 8503 --server.headless true --browser.gatherUsageStats false
pause
