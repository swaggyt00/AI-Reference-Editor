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

REM Use a private FFmpeg copy in the project folder if available.
set "LOCAL_FFMPEG=%~dp0tools\ffmpeg\bin"
if exist "%LOCAL_FFMPEG%\ffmpeg.exe" set "PATH=%LOCAL_FFMPEG%;%PATH%"

where ffmpeg >nul 2>&1
if errorlevel 1 goto :install_ffmpeg
where ffprobe >nul 2>&1
if errorlevel 1 goto :install_ffmpeg
goto :ffmpeg_ready

:install_ffmpeg
echo [0/3] FFmpeg missing. Downloading and installing a local copy...
where powershell >nul 2>&1
if errorlevel 1 (
  echo ERROR: Windows PowerShell not found. Unable to download FFmpeg.
  goto :fail
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_ffmpeg.ps1" -ProjectRoot "%CD%"
if errorlevel 1 goto :fail
set "PATH=%LOCAL_FFMPEG%;%PATH%"
where ffmpeg >nul 2>&1
if errorlevel 1 goto :fail
where ffprobe >nul 2>&1
if errorlevel 1 goto :fail

:ffmpeg_ready

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
      echo   https://www.python.org/downloads/windows/
      echo Select Python 3.11 or later, check "Add Python to PATH".
      echo Close and reopen this script after installation.
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
