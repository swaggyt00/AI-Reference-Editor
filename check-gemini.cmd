@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Reference Editor - Gemini connection diagnostic
echo.
echo =========================================
echo GEMINI CONNECTION CHECK - NO KEY RE-ENTRY
echo =========================================
echo.
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Python environment not found. Start start-editor.cmd first.
  goto :fail
)
if not exist "secrets\gemini.key" (
  echo ERROR: Encrypted Gemini key not found. Run configure-gemini.cmd once.
  goto :fail
)
echo [1/2] Checking saved key and SDK locally (ZERO API requests)...
".venv\Scripts\python.exe" -m refeditor ai-check --local-only
if errorlevel 1 goto :fail
echo.
echo Local key check OK.
echo [2/2] Google API test (ONE SMALL REQUEST ONLY).
echo Gemini 3.8 Flash previously returned HTTP 503.
echo Gemini 3.6 Flash supports video and has a documented free tier.
choice /c YN /n /m "Test Gemini 3.6 Flash instead? [Y/N]: "
if errorlevel 2 goto :ok
".venv\Scripts\python.exe" -m refeditor ai-check --model gemini-3.6-flash
if errorlevel 1 goto :fail
:ok
echo.
echo Diagnostic finished. No video was uploaded.
echo NOTE: This tests the fallback model; it does not change the default model.
pause
exit /b 0
:fail
echo.
echo Diagnostic stopped. No API key was displayed.
pause
exit /b 1
