@echo off
rem Triage kiosk prototype in DEMO mode (draft rules; synthetic / sample data only). Close this window to stop.
cd /d "%~dp0"
start "" http://localhost:8502
".venv\Scripts\python.exe" -m streamlit run src\triage\kiosk_app.py --server.port 8502 --server.headless true --browser.gatherUsageStats false -- --demo
pause
