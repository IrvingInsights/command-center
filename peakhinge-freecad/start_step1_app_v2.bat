@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py scripts\step1_chat_server_v2.py
) else (
  python scripts\step1_chat_server_v2.py
)
