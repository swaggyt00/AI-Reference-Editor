# Codex Web — запуск AI Reference Editor

## 1. Connect the repository

1. Open https://chatgpt.com/codex using an account with Codex Cloud access.
2. Connect GitHub (if needed) and authorize swaggyt00/AI-Reference-Editor for Codex.
3. Create a cloud Environment with repository swaggyt00/AI-Reference-Editor, branch main.
4. In the Environment setup settings, enter the setup script command:
    bash scripts/setup_cloud.sh
5. Save/publish the Environment and choose it in a new Codex cloud task.

Setup requires package installation permissions (Python dependencies and FFmpeg); inspect any setup errors and allow necessary access during setup.

## 2. First run WITHOUT videos

Send the following task to Codex:

Read AGENTS.md, README.md and WEB_CODEX.md. Run python -m unittest discover -s tests -v and python -m refeditor doctor. Report dependency errors, if any. Do not claim video editing has already run or automatically detect complex VFX that the current code cannot analyze.

## 3. Run on actual videos

This GitHub repository contains CODE ONLY, not private reference/source MP4s. Codex Cloud does NOT automatically see videos on the user's PC or in an ordinary ChatGPT conversation.

Make input files available inside the Codex task workspace (for example through a securely hosted temporary direct download URL accessible from the environment, or a separate upload tool). Keep private videos out of this PUBLIC repository.

Once files exist inside the workspace, e.g. input/reference.mp4 and input/clip1.mp4 and input/clip2.mp4:

    python -m refeditor pipeline --reference input/reference.mp4 --sources input/clip1.mp4 input/clip2.mp4 --output-dir output --mode fit

Expected outputs: output/final.mp4, output/project.json, output/comparison.jpg, output/qa_report.json. Ask Codex to inspect the result and expose available output artifacts through the task UI.

WARNING: There is NOT YET an upload-and-render web page. Codex Web is currently a cloud software development environment that runs Python scripts, not an end-user video editor. A separate upload UI/storage/delivery workflow is future work.

## 4. Next development priorities

Build a user-friendly secure upload/output flow for large videos. Add reference-aware zoom, motion blur, speed ramp, transition analysis and semantic shot matching, with measurable confidence and a comparison loop. Do not invent detected effects.
