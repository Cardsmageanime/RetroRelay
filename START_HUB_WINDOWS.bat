@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv
    if errorlevel 1 (echo Install Python 3.11+ first. & pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
echo Starting RetroRelay HUB at http://127.0.0.1:8751 ...
.venv\Scripts\python.exe server.py
pause
