@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AI Reference Editor - Motion Design setup
echo.
echo MOTION DESIGN - one-time optional installation
echo No Codex or cloud video server required.
echo.
if exist "tools\node\node.exe" set "PATH=%CD%\tools\node;%PATH%"
where node >nul 2>&1
if errorlevel 1 (
  echo Downloading local Node.js and verifying its official checksum...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\install_node.ps1" -ProjectRoot "%CD%"
  if errorlevel 1 goto :fail
  set "PATH=%CD%\tools\node;%PATH%"
)
where npm >nul 2>&1
if errorlevel 1 goto :fail
echo Installing Remotion library dependencies...
pushd motion
call npm.cmd install --no-audit --no-fund
set "result=%errorlevel%"
popd
if not "%result%"=="0" goto :fail
echo.
echo Ready. Motion Design can be enabled on GitHub Pages.
echo Restart start-editor.cmd before editing.
pause
exit /b 0
:fail
echo.
echo Setup failed. Check the console for exact reason.
pause
exit /b 1
