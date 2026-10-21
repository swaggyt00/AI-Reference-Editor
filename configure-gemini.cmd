@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Reference Editor - Gemini setup
echo ==========================================================
echo Configure Gemini API key on YOUR PC - not on GitHub Pages.
echo ==========================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\set-gemini-key.ps1" -ProjectRoot "%CD%"
if errorlevel 1 goto :fail
echo.
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: The local editor virtual environment was not found.
  echo First run start-editor.cmd once, then run configure-gemini.cmd.
  goto :fail
)
echo Installing the optional Gemini SDK...
".venv\Scripts\python.exe" -m pip install -r requirements-ai.txt
if errorlevel 1 goto :fail
echo.
echo API key encrypted, Gemini SDK installed.
echo To test with ONE small API request press Y; to skip, press N.
choice /c YN /n /m "Test connection now? [Y/N]: "
if errorlevel 2 goto :success
".venv\Scripts\python.exe" -m refeditor ai-check
if errorlevel 1 goto :fail
:success
echo.
echo Configuration is complete. No video was uploaded.
pause
exit /b 0
:fail
echo.
echo Gemini setup failed. Key may still have been saved locally.
pause
exit /b 1
