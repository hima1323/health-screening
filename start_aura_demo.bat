@echo off
rem Aura Screen + reasoning model demo for presentations (sample data, draft rules). Close the two windows to stop.
rem The server starts the reasoning model itself (reasoning_model\.venv).
rem   phone (same Wi-Fi): https://<this laptop IP>:5173 (accept the certificate warning once), sign in, press
rem   Begin contactless scan and scan a printed code from docs\demo-qr. Needs MongoDB (the Scan Hub reads the station).
cd /d "%~dp0"
start "Aura server" /d "%~dp0server" cmd /k "node index.js"
start "Aura app (https)" /d "%~dp0client" cmd /k "set HTTPS=1&& npx vite"
echo Waiting for the app to start...
timeout /t 8 /nobreak >nul
start "" "https://localhost:5173/"
echo.
echo Phone (same Wi-Fi): open https://YOUR-LAPTOP-IP:5173  - your IP addresses:
ipconfig | findstr /r /c:"IPv4"
pause
