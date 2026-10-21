# AI Reference Editor — Codex agent instructions

You are improving a reference-driven editor for a user who supplies a finished reference video and DIFFERENT source footage. Match reference montage grammar, cuts, motion rhythm, masks, VFX and sound as faithfully as evidence permits. Do not add effects absent from the reference.

## Rules

1. Inspect actual video material before claiming an effect or action was detected. Never fabricate temporal detail or missing shots.
2. Clearly separate AUTOMATIC extraction from effects only available via MANUAL JSON recipe. Current code automatically extracts hard cuts, digital black side masks and limited flash candidates; zoom, blur, shake, speed keyframes and color effects are supported for rendering but NOT automatically detected.
3. Favor precise source selection, matching shot composition/motion and sound over decorative effects. No generic SFX layers or random jump cuts.
4. Preserve original media and put generated files under output/ or a temporary directory.
5. Check the rendered final.mp4, visual comparison, boundaries, durations and audio; technical QA alone does not establish senior creative quality.
6. Never call a result “1:1” if the user supplies different footage and the movements do not match.
7. Keep Python+FFmpeg cross-platform; do not require CapCut.
8. Repo omits private original MP4 files. Do not expect demo files to exist in Codex Cloud. Do not claim upload feature already exists. See WEB_CODEX.md.

## Setup / commands

- bash scripts/setup_cloud.sh — dependencies (Codex/Linux).
- python -m unittest discover -s tests -v — unit suite.
- python -m refeditor doctor — runtime check.
- python -m refeditor analyze --reference input/reference.mp4 --output output/analysis.json — extract signals.
- python -m refeditor pipeline --reference input/reference.mp4 --sources input/clip1.mp4 input/clip2.mp4 --output-dir output --mode fit — render with actual files.
- python -m refeditor render --project output/project.json --output output/revised.mp4 — rerender.

## Feature status

Implemented: cuts; black vertical masking; limited bright-flash candidates; chronological source mapping; optional FFT alignment if audio matches; JSON effect recipes; rendering; technical QA/contact sheet.

Not implemented: semantic shot retrieval; automatic zoom/blur/shake/speed-ramp detection; object-level VFX/tracking; generative missing scenes; senior-level creative judgment; web UI/upload.

## Roadmap

1. Add reproducible synthetic integration media/test independent from user's files.
2. Add semantics-driven shot retrieval, robust timeline detection, real effect classification and parameter estimation (with confidence and abstention).
3. Add automated visual/audio critique and revision loop, evaluated on real paired examples.
4. Add secure upload storage + web UI + rendered file delivery to make it a practical browser-based editor.

Always run tests and a real render when video input is available. Fix regressions without removing working features.
