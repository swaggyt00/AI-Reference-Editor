#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  if command -v apt-get >/dev/null; then
    echo 'FFmpeg missing; trying apt-get (environment must permit installs)'
    if [ "$(id -u)" = 0 ]; then apt-get update && apt-get install -y ffmpeg; else sudo apt-get update && sudo apt-get install -y ffmpeg; fi
  else
    echo 'ffmpeg/ffprobe not found and no apt-get available. Install them in the Codex environment.' >&2; exit 1
  fi
fi
python -m pip install -r requirements.txt
python -m refeditor doctor
python -m unittest discover -s tests -v
