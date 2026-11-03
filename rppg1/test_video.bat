@echo off
rem Heart rate from a video file. Drag a video onto this file, or: test_video.bat my_face.mp4 [model]
rem models: p4 (default), p4-12-flip, p4-12, physformer, all
cd /d "%~dp0"
set PY=%~dp0..\reasoning_model\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
if "%~1"=="" (
  "%PY%" -m bench.infer --list
  echo.
  echo Drag a video file onto test_video.bat to measure it.
  pause
  exit /b
)
set MODEL=%~2
if "%MODEL%"=="" set MODEL=all
"%PY%" -m bench.infer --video "%~1" --model %MODEL% --plot "%~dpn1_pulse.png"
pause
