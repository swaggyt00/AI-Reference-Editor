@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Reference Editor - Windows Render Engine

echo.
echo ==========================================================
echo AI REFERENCE EDITOR - WINDOWS LOCAL RENDER ENGINE
echo ==========================================================
echo.
echo This program renders on YOUR PC only.
echo Keep this window open while using the GitHub Pages editor.
echo Your videos are NOT uploaded to GitHub or cloud.
echo.

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo ERROR: FFmpeg not found in PATH.
  echo Install once using Windows Terminal:
  echo   winget install -e --id Gyan.FFmpeg
  echo Then CLOSE and reopen the terminal and run this file again.
  goto :fail
)
where ffprobe >nul 2>&1
if errorlevel 1 (
  echo ERROR: ffprobe missing. Reinstall FFmpeg with:
  echo   winget install -e --id Gyan.FFmpeg
  goto :fail
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating Python virtual environment...
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    where python >nul 2>&1
    if errorlevel 1 (
      echo ERROR: Python 3 not installed.
      echo Install once using Windows Terminal:
      echo   winget install -e --id Python.Python.3.11
      echo Close and reopen the terminal after installation.
      goto :fail
    )
    python -m venv .venv
  )
  if errorlevel 1 goto :fail
)

echo [2/3] Checking/installing local dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [3/3] Checking engine...
".venv\Scripts\python.exe" -m refeditor doctor
if errorlevel 1 goto :fail

echo.
echo Ready. Browser website:
echo   https://swaggyt00.github.io/AI-Reference-Editor/
echo.
echo In Chrome click "Connect PC" and approve local network access.
echo IMPORTANT: NEVER launch multiple server windows simultaneously.
echo To stop the engine press Ctrl+C here, then Y if asked.
echo.

start "" "https://swaggyt00.github.io/AI-Reference-Editor/"
".venv\Scripts\python.exe" -m refeditor web --host 127.0.0.1 --port 8000 --storage output/web
if errorlevel 1 goto :fail
goto :end

:fail
echo.
echo Setup or server launch FAILED. Read the error above.
echo See WINDOWS_PAGES_SETUP.md for help.
pause
exit /b 1

:end
echo The local render server stopped.
pause
