@echo off
rem Live webcam heart rate in the browser (Streamlit). Close this window to stop.
cd /d "%~dp0"
set PY=%~dp0..\reasoning_model\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
start "" http://localhost:8501
"%PY%" -m streamlit run webapp\streamlit_app.py
pause
