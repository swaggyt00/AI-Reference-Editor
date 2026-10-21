# AI Reference Editor — Codex MVP

Reference-based video editing with DIFFERENT source footage, using Python, OpenCV and FFmpeg. No CapCut is needed. Designed for iterative development in Codex Web or local Codex.

Current scope: automatically finds some hard cuts, digital black edge masks and limited flash candidates, maps source clips chronologically to reference sections, optionally aligns audio when soundtracks overlap, renders MP4 and produces technical QA and visual comparison. Zoom, blur, shake, color and speed curve effects can be hand-authored in project JSON but ARE NOT automatically inferred.

This is a working experimental engine, NOT a fully autonomous senior video editor.

**Codex Web setup:** see WEB_CODEX.md. Original personal reference and source videos are intentionally not included in the public repository.

## Requirements

Python 3.11+, FFmpeg and ffprobe, Python dependencies in requirements.txt.

    python -m pip install -r requirements.txt
    python -m refeditor doctor
    python -m unittest discover -s tests -v

For Codex Cloud / Linux you can run:

    bash scripts/setup_cloud.sh

## Editing your videos

    python -m refeditor analyze --reference input/reference.mp4 --output output/analysis.json
    python -m refeditor pipeline --reference input/reference.mp4 --sources input/clip_01.mp4 input/clip_02.mp4 --output-dir output --mode fit

Modify output/project.json and render again:

    python -m refeditor render --project output/project.json --output output/revised.mp4

Results: output/final.mp4, output/project.json, output/comparison.jpg and output/qa_report.json.

**Current limits:** the source-to-shot matcher is chronological, not semantic. With short footage, fit mode changes speed and native mode holds a frame. Missing actions will not be generated. Audio from the reference is reused only when permitted; it is not automatically remixed.

### Optional manually prescribed effects

Set effects in the generated project.json ONLY if verified in the reference. For instance, an effect recipe for zoom has type zoom, start, end, from, to and optional easing; blur has a sigma from/to; flash has strength; shake has amplitude_px and frequency_hz. Color uses contrast, brightness and saturation. Each segment can have speed_keyframes with at (normalized target time from 0 to 1) and speed. These are supported rendering recipes, not automatic detections.

## Demo data

The four reference/source MP4s from the initial experiment are NOT COMMITTED because the repository is public. To run the same demo, you would need to place authorized copies at these paths:
- demo/reference_01.mp4
- demo/reference_04.mp4
- demo/source_02.mp4
- demo/source_03.mp4

Then run bash run_demo.sh (Linux/macOS) or run_demo.bat (Windows). Otherwise run pipeline with your own files.

## Limitations / roadmap

Not yet implemented: semantic shot matching; automatic zoom, speed ramp, motion blur or object-based effect detection; full sound design; generative shot completion; browser upload page; persistent media storage and human-level creative quality evaluation.

AGENTS.md contains instructions for further Codex development. WEB_CODEX.md contains practical cloud steps.
