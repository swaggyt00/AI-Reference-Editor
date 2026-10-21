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
echo [2/2] You can make ONE small API request to verify model access.
choice /c YN /n /m "Make API request now? [Y/N]: "
if errorlevel 2 goto :ok
".venv\Scripts\python.exe" -m refeditor ai-check
if errorlevel 1 goto :fail
:ok
echo.
echo Diagnostic finished. No video was uploaded.
pause
exit /b 0
:fail
echo.
echo Diagnostic stopped. NO API key has been displayed.
pause
exit /b 1
