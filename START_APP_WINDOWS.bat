@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv
    if errorlevel 1 (echo Install Python 3.11+ first. & pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
.venv\Scripts\python.exe -m pip install -r requirements-client.txt
if errorlevel 1 echo Optional gamepad scan unavailable: install pygame to enable it.
.venv\Scripts\python.exe client.py
if errorlevel 1 pause
