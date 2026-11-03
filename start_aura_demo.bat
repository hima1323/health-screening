@echo off
rem Aura Screen + reasoning model demo for presentations (sample data, draft rules). Close the three windows to stop.
rem   kiosk screen (laptop):  https://localhost:5173/kiosk?demo=1
rem   phone (same Wi-Fi):     https://<this laptop IP>:5173/demo   (accept the certificate warning once)
cd /d "%~dp0"
if not exist reasoning_model\demo_samples\*.json (
  pushd reasoning_model\src & "%~dp0reasoning_model\.venv\Scripts\python.exe" -m triage.demo_samples --build & popd
)
start "Aura reasoning service" /d "%~dp0reasoning_model\src" "%~dp0reasoning_model\.venv\Scripts\python.exe" -m triage.demo_service
start "Aura server" /d "%~dp0server" cmd /k "set DEMO_WITHOUT_DB=1&& node index.js"
start "Aura app (https)" /d "%~dp0client" cmd /k "set HTTPS=1&& npx vite"
echo Waiting for the app to start...
timeout /t 8 /nobreak >nul
start "" "https://localhost:5173/kiosk?demo=1"
echo.
echo Phone (same Wi-Fi): open https://YOUR-LAPTOP-IP:5173/demo  - your IP addresses:
ipconfig | findstr /r /c:"IPv4"
pause
