@echo off
rem Benchmark test on the preprocessed datasets (MCD held-out subjects, UBFC, MPSC).
rem usage: run_benchmark.bat [model] [sets]   e.g. run_benchmark.bat p4 ubfc   (default: all models, all sets)
cd /d "%~dp0"
set PY=%~dp0..\reasoning_model\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
set MODEL=%~1
if "%MODEL%"=="" set MODEL=all
shift
"%PY%" -m bench.infer --benchmark %1 %2 %3 --model %MODEL%
pause
