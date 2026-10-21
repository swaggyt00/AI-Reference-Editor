@echo off
cd /d "%~dp0"
if not exist demo\reference_01.mp4 goto nofiles
if not exist demo\source_02.mp4 goto nofiles
if not exist demo\source_03.mp4 goto nofiles
py -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
py -m refeditor doctor
if errorlevel 1 exit /b 1
py -m refeditor pipeline --reference demo/reference_01.mp4 --sources demo/source_02.mp4 demo/source_03.mp4 --output-dir output --mode fit
exit /b %errorlevel%
:nofiles
echo Demo MP4 files are not included in GitHub. See README.md and WEB_CODEX.md.
exit /b 2
