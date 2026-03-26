@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py scripts\launch_step1_app.py
) else (
  python scripts\launch_step1_app.py
)
