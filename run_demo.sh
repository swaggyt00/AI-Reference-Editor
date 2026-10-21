#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f demo/reference_01.mp4 ] || [ ! -f demo/source_02.mp4 ] || [ ! -f demo/source_03.mp4 ]; then
  echo 'Demo MP4 files are not included in GitHub. See README.md and WEB_CODEX.md.' >&2
  exit 2
fi
python3 -m pip install -r requirements.txt
python3 -m refeditor doctor
python3 -m refeditor pipeline --reference demo/reference_01.mp4 --sources demo/source_02.mp4 demo/source_03.mp4 --output-dir output --mode fit
