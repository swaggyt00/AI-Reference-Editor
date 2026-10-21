# AI Reference Editor — Codex MVP

## Internet Editing Intelligence (online knowledge, zero video library)

**No reference-video training collection on your PC.** The editor's new research
mode works with public **documentation metadata**, not downloaded YouTube clips,
full tutorials or footage. Its text index is published openly at
[`docs/knowledge.json`](docs/knowledge.json) in GitHub, never a local media database.

- Seeded with 18 official technical resources: Remotion transitions, timing,
  motion blur, captioning, graphic animation, audio, FFmpeg and OpenCV.
- A GitHub Actions workflow (`learn-online.yml`) runs **Monday and Thursday**
  and may be triggered manually in GitHub Actions. It checks allowlisted
  documentation pages for changes and discovers **up to four new official
  documentation pages per run**, at most 60 total. No videos, images,
  articles, scripts, or third-party executable code are downloaded into the
  index; it stores brief titles, descriptions, headings, links, and status.
- When Gemini is already enabled for a user-approved edit, Python fetches
  the **small JSON text index in memory** from the public GitHub repository,
  selects up to six relevant references and includes them in the AI
  director/highlights prompt. If GitHub is unreachable, bundled notes are used.
- Sources distinguish **`implemented` vs `research_only`**. Learning that
  an effect exists does NOT add its implementation automatically or guarantee
  an exact reference clone. LLM weights are not fine-tuned and no arbitrary web
  instructions are treated as commands.
- **Privacy:** no Gemini key is used by GitHub Actions. The knowledge refresh
  never touches user media. During actual editing, original user-uploaded
  videos **are still processed and stored in `output/web` on the Windows
  render machine until manually removed**; no learning-video archive is created.
  The existing consent is required for sending compressed video/audio proxies
  or storyboards to Gemini. This change does not automatically delete editing
  projects or exports.

This is the **first online research layer**, not a self-training senior editor:
creative quality still requires real end-to-end evaluation against references.
The remote workflow depends on GitHub Actions being enabled and may be delayed
or skipped by GitHub scheduling. Source availability and provider quotas can
change.


## Graphic reconstruction v3 — evidence-first overlays

In **Reference Clone + Gemini + Motion Design**, the director now sends up to
**three local storyboards of time-coded frames** (max 48 still frames) to the
existing Gemini edit-plan request. This is a visual input within the same model
request, NOT a separate AI call, but it can increase image-token usage. The
browser explicitly asks consent for these storyboard images along with the
compressed reference/source videos and audio. Original media remains local.

A motion plan can now include validated global-time keyframes for horizontal
position, vertical position, scale and opacity, observed color/typography
alignment, and candidate reference graphics. Text and route overlays must cite
an actual storyboard frame index; other hallucinated overlays are discarded.

The new local **Graphic Extractor** can reuse a simple icon, pixel-art sticker
or logo from the actual reference IF:
1. Gemini identifies a qualifying category, bounding box and sample time that
   coincide with an actual storyboard frame, with confidence >=0.84;
2. OpenCV verifies either a uniform backdrop around the graphic, or almost
   unchanged adjacent clean-plate footage with the graphic missing; and
3. The extracted PNG alpha passes minimum-size and foreground-coverage gates.

Rejected candidates are logged under the local render folder at
`graphic-assets/graphic-analysis.json`. Extracted PNGs and intermediate
storyboard JPEGs remain on the PC, not in GitHub. Neither Google nor the system
can reliably reconstruct hidden artwork, 3D, moving-camera rotoscoping,
complex alpha shadows or After Effects source layers from a flattened MP4.
There is NO claim of pixel-perfect video reproduction.

The 76-second supplied reference was checked **locally** against the new
storyboard generator: it produced 39 timestamped stills in three sheets.
The creative AI / real Gemini / Windows end-to-end run remains **unverified**,
because the API key never leaves the user's PC. Offline tests cover the
storyboard construction, safe alpha extraction and rejection, keyframes,
and a mocked Gemini image+text edit-plan request.

## Motion Design — prototype in development

The new **Motion Design (beta)** mode extends Reference Clone using a Remotion
compositor on the same Windows computer. It supports bounded, timeline-driven
layers, including kinetic titles, captions, badges, information cards, abstract
(animated) route diagrams, uploaded image overlays and B-roll video windows.
Video windows use only material actually supplied by the user. Other source clips
remain on the PC. Existing audio is preserved during overlay composition.

**Install separately once:** double-click `setup-motion.cmd` (downloads Node.js
from the official site after verifying SHA-256, then installs pinned Remotion
packages) and restart `start-editor.cmd`. This does NOT require `winget`,
paid cloud video rendering or Codex. Keep `tools/node` and `motion/node_modules`
between restarts. This optional renderer is never required for normal edits.

**Use:** Reference Clone + Gemini AI enabled + Motion Design checked. The model
proposes a typed JSON motion plan based on actual graphics it finds in reference
and source footage; the local Python validator rejects invalid/uncertain entries
before Remotion creates the layers. Motion Design has a pilot limit of 120
seconds per file and 40 reference shots, up to 3 source videos. The AI stage
may consume free-tier requests and the remote video proxies include audio;
the user confirms before Google upload.

**Honest limitations:** This is only the first compositor milestone. It cannot
yet reconstruct arbitrary After Effects projects, complex 3-D animation,
rotoscoping, object tracking, backgrounds hidden by foreground objects, or
accurately infer every font, title, transition or layered B-roll from a finished
MP4. A picture-in-picture or custom media insert requires actual uploaded
footage. A 76-second benchmark may need original graphics and additional
media assets. The result needs visual review; do not assume pixel-perfect
1:1 replication.

**Remotion license:** Remotion is free for individuals and eligible small teams
under its license. Larger commercial teams may require a paid company license.
https://www.remotion.dev/docs/license

Local smoke tests under GitHub Actions run real Remotion/Chromium rendering
with synthetic media and verify its MP4 video+audio output. Gemini's actual
video understanding needs the user's own encrypted Windows key, and is not
simulated as "passed" for real creative editing quality.

## GitHub Pages + Windows

The public HTML/JS frontend runs on **GitHub Pages**; all private video uploads and FFmpeg processing happen on **your own Windows machine** at `127.0.0.1:8000`, not on GitHub servers. Codex is not needed for everyday rendering.

- Web address (after one-time Pages activation): https://swaggyt00.github.io/AI-Reference-Editor/
- One-time setup: [WINDOWS_PAGES_SETUP.md](WINDOWS_PAGES_SETUP.md).
- Download source ZIP, unpack, double-click `start-editor.cmd`; on the Pages site press **«Подключить ПК»** and grant Chrome loopback-network permission.
- In GitHub repo Settings -> Pages -> source **Deploy from a branch** -> `main` -> `/docs` -> Save.
- Pages is a static host, not a video server. The local engine works only when this PC is on with the launcher running.


Reference-based video editing with DIFFERENT source footage, using Python, OpenCV and FFmpeg. No CapCut is needed. Designed for iterative development in Codex Web or local Codex.

Current scope: two experimental modes — **Reference Clone** (hard cuts, black edge masks, measured light-gray door/panel overlays copied from reference frames, conservative bright flashes, optional shared-audio alignment and Gemini scene matching) and **Smart Reels** (Gemini highlight proposals for one long video and local FFmpeg vertical montage with optional music). Zoom, blur, shake, color and speed curves can be authored in project JSON but ARE NOT automatically inferred. Complex 1:1 VFX and cinematic judgement are NOT guaranteed.

This is a working experimental engine, NOT a fully autonomous senior video editor.

**Codex Web setup:** see WEB_CODEX.md. Original personal reference and source videos are intentionally not included in the public repository.

## Requirements

Python 3.11+, FFmpeg and ffprobe, Python dependencies in requirements.txt.

    python -m pip install -r requirements.txt
    python -m refeditor doctor
    python -m pip install -r requirements-dev.txt
    python -m unittest discover -s tests -v

For Codex Cloud / Linux you can run:

    bash scripts/setup_cloud.sh

## Optional Gemini AI video understanding (no Codex required)

**Status:** Gemini `gemini-3.6-flash` is now integrated as an **opt-in experimental source-scene matcher** in the browser editor. It analyzes video descriptions, proposes shot-to-source matches and source starting times, validates confidence and uses reliable shared-audio matches as higher-priority evidence. It still **cannot reproduce complex VFX automatically** or guarantee senior-level editing; mask/cut timing remains handled locally by OpenCV.

1. Get your own API key from Google AI Studio. Never paste it in chat or GitHub.
2. On Windows, unpack the latest repository code into your installed project directory, keeping local `.venv`, `tools` and `output` folders.
3. Double-click `configure-gemini.cmd`, paste the key at its hidden PowerShell prompt and choose whether to make one tiny API test request.
4. Windows DPAPI encrypts the key at `secrets/gemini.key` for your Windows user profile. This directory is gitignored.
5. To analyze a video **only when you authorize upload to Google**:

```powershell
.\.venv\Scripts\python.exe -m refeditor ai-analyze --video "C:\Videos\reference.mp4" --role reference --output "output\reference-semantic.json" --confirm-external-upload
```

The stand-alone ai-analyze command generates a smaller MP4 proxy, uploads **that proxy** with audio to Gemini Files API, requests scene/action and effect observations, then attempts to delete the cloud copy. In the browser's Reference Clone Gemini provides source-scene matching as an explicit opt-in; it does not automatically invent or execute arbitrary complex VFX.

### New v2 modes — experimental

**Reference Clone:** upload one reference and one or more sources. Optionally
enable Gemini to match scenes by subjects, actions and composition. A reference
effect transfer pass copies measurable hard-cut timing, digital black edges,
**gray/white moving side panels sampled from the actual reference frames** and
high-confidence flashes. This is not full 1:1 VFX cloning; particle effects,
motion graphics, camera tracking, color grading and motion-blur estimation are
not implemented. Unreliable automatic matches are ignored.

**Smart Reels:** choose this mode in the editor, upload **one** source video
of 15 seconds to 30 minutes, optionally upload your own MP3/WAV/AAC music,
set **10–90 seconds** for the output and check the Gemini consent checkbox.
A compressed proxy of the ENTIRE original with audio is sent to Google. Gemini
returns approximate highlight time ranges and a story outline. Python rejects
overlapping or invalid ranges; FFmpeg cuts the *original* footage into
a 9:16 H.264 MP4 (720×1280 / 30 fps), preserving the source voice and mixing
music at roughly -17 dB relative to nominal full scale. Export and intermediate
media remain on your PC. You must review the storytelling and dialogue cuts.

**IMPORTANT limitations:** It is a center-crop vertical frame, with no face/actor
tracking. It doesn't beat-sync cuts, generate subtitles or identify every
complex effect. Underlying model timestamps are approximate, and the free-tier
API does not guarantee video capacity or request completion. A 15-minute
original can be expensive in free-tier token/quota terms, even as a low-res
proxy; the engine never falls back to paid providers automatically.

**Testing:** offline GitHub CI runs a real FFmpeg synth-video audio mix and
tests the Smart Reels local HTTP endpoints with a MOCKED Gemini plan. Your
actual AI Studio key and end-to-end Gemini video calls are not available to CI,
and must be tested separately by you on Windows before trusting final results.

**Installation:** Get the latest ZIP from the repo, replace the existing
code files but retain the existing `secrets/`, `tools/`, `.venv/` and `output/`.
Restart `start-editor.cmd` and hard-refresh GitHub Pages. You should see a
mode selector and the optional music picker.

### Browser AI pilot

The newest GitHub Pages front end has a checkbox **«AI-подбор сцен через Gemini»**.
You must explicitly tick this and confirm each time before *any* video goes to Google.
The preview upload includes downsampled video and original audio in lower bitrate; original
media and final render remain on the Windows computer. The local API key is **never
sent to the page**.

The pilot supports **1 reference + up to 3 sources**, each **up to 60 seconds**,
and **12 reference shots**. When semantic analysis is first needed, Gemini processes
each compressed preview separately and performs one director-matching API request.
Subsequent renders reuse local cached per-video semantic analyses when possible
(still using a new text-only director call). This MAY use several API requests per
project; quotas are not guaranteed and your own provider billing settings apply.
If Gemini returns an error, AI mode reports failure clearly: switch AI off to
use ordinary deterministic rendering.

Scene matches below 0.65 confidence are ignored; stronger shared-audio evidence
is preserved. AI may choose the wrong moments — inspect project.json and the final
comparison. The model can list suspected effects, but those observations are
**NOT yet executed**. The free-text brief is provided as a hint for the semantic
matching prompt, not as an unrestricted command interpreter.

Existing installs: copy the latest repo files over your project installation,
**keeping `.venv`, `secrets`, `tools` and `output`** and restart
`start-editor.cmd`. Confirm the page displays the AI checkbox before testing.

**Cost and privacy:** Google may limit free-tier calls. This code cannot verify that your AI Studio project has no billing or guarantee zero charge. Ensure your selected model/project is on the free tier before calling. Free-tier data may be used by the provider to improve services. Ordinary non-AI renders send no video to Google. Exact availability of free-tier models depends on region/account; errors are returned when quota or access is unavailable.

## Browser editor

Start the local web interface (no Node.js or frontend build required):

    python -m refeditor web

Open **http://127.0.0.1:8000**. Select or drop one reference and multiple source videos, arrange the source order, enter a brief and choose speed/audio settings. Click **«Анализировать и смонтировать»**. Upload progress and background analysis/render stages are displayed; completed MP4s support preview, seeking and download. Change the settings, source selection/order or brief and click **«Повторить рендер»** to create a new version using the same uploads. Previous versions remain available.

The page restores the last project after refresh; its URL fragment contains the project ID and can be bookmarked. Completed uploads, render metadata and results persist under `output/web/<project-id>/`. Unfinished uploads must be selected again after refresh. Interrupted renders are marked failed on server restart and can be retried. To use a different reference, start a new project. Removing a source from the edit retains it for earlier versions; use **«Вернуть загруженные исходники»** to select it again.

### Text brief: explicit commands, not general AI interpretation

The brief is saved in each version's `project.json`. Only these exact command lines are currently executed; one value per line:

    звук: нет
    режим: native
    длительность: 15

`звук` accepts `нет`, `референс`, or `исходник`; `режим` accepts `fit` or `native`; `длительность` accepts seconds (decimal comma or point). Commands override the corresponding form settings. Duration is an end trim, capped by reference duration; it does not regenerate pacing or extend the reference. Other text is preserved and visibly reported as **not automatically executed**. There is no LLM service or API key dependency.

Audio defaults to none. Select reference audio only when permitted. Source audio uses the first selected source from its beginning, not a per-shot sound mix. Optional audio alignment is only for recordings that actually share sound. The existing chronological mapper can use fewer sources than supplied; with a single reference shot it selects the last source. The interface reports unused sources.

### Storage and launch options

    python -m refeditor web --port 8000 --storage output/web --max-upload-mb 2048

- Default limits: 2 GiB per uploaded file, 10 GiB of uploaded media per project, 32 stored sources plus one reference; each video up to 60 minutes, 4096×2160 pixels and 120 fps. Render versions require additional disk space. Source formats must be decodable by the installed FFmpeg **and** OpenCV; invalid files and playlists are rejected. No fixed filenames or example footage are required.
- Uploads stream to disk with generated names, actual media validation and byte limits; completed upload retries are idempotent. File delivery is restricted to completed render artifacts. Mutating API requests require a custom header and same-origin checks.
- **Local, single-user service:** one server process and one render worker per storage directory. Default binding is loopback. There are no user accounts, public hosting authentication, automatic retention cleanup or distributed job queue. Do not expose it directly to the Internet; remote deployment needs an authenticated TLS proxy, upload limits/timeouts and disk quotas. `--host` is available for a trusted, protected environment.
- Stop the server before manually archiving or deleting old project directories. Starting a new project does not delete the previous one. Original uploads and render artifacts are ignored by git.
- H.264 output with odd source dimensions is padded by at most one pixel on the right/bottom for browser compatibility. Reference/source selection, manual effect recipes and all previous CLI commands remain supported. The web form rebuilds the timeline from its settings; manual JSON recipes are edited and rerendered via the CLI.

### Verification

    python -m pip install -r requirements-dev.txt
    python -m unittest discover -s tests -v

The suite generates fresh synthetic media and tests real FFmpeg renders, cuts/masks, audio, upload validation, download ranges, revision preservation, failure recovery and interrupted-state recovery. It does not need old user videos.

For a browser acceptance test, run the server in one terminal, then in another:

    python -m playwright install chromium
    python scripts/test_web_browser.py --url http://127.0.0.1:8000

An installed Chromium can be selected with `--browser /path/to/chromium`. The test covers uploads, ordering, playback/download, reload, rerender/history, source reselection, lost upload response recovery and mobile width; generated media/screenshots are saved under `output/browser-check/`. It creates disposable projects on the supplied server, so use a test storage directory when needed.

## Editing your videos

    python -m refeditor analyze --reference input/reference.mp4 --output output/analysis.json
    python -m refeditor pipeline --reference input/reference.mp4 --sources input/clip_01.mp4 input/clip_02.mp4 --output-dir output --mode fit

Modify output/project.json and render again:

    python -m refeditor render --project output/project.json --output output/revised.mp4

Results: output/final.mp4, output/project.json, output/comparison.jpg and output/qa_report.json.

**Current limits:** the source-to-shot matcher is chronological, not semantic. With short footage, fit mode changes speed and native mode holds a frame. Missing actions will not be generated. Audio from the reference is reused only when permitted; it is not automatically remixed.

### Optional manually prescribed effects

Set effects in the generated project.json ONLY if verified in the reference. For instance, an effect recipe for zoom has type zoom, start, end, from, to and optional easing; blur has a sigma from/to; flash has strength; shake has amplitude_px and frequency_hz. Color uses contrast, brightness and saturation. Each segment can have speed_keyframes with at (normalized target time from 0 to 1) and speed. These are supported rendering recipes, not automatic detections.

## Universal workflow — any videos

This repository is an **engine**, not a packaged demo for a fixed set of videos. Every editing job uses freshly supplied inputs:

- One or more reference videos to study; the current CLI analyzes one reference per run.
- Any number of independent source footage clips; the current CLI accepts all paths supplied after `--sources`.
- A task brief specifying the requested duration, pacing, edit style, and sounds.

Example using **arbitrary paths**:

    python -m refeditor pipeline --reference "/workspace/job_42/reference.mp4" --sources "/workspace/job_42/shots/a.mov" "/workspace/job_42/shots/b.mp4" "/workspace/job_42/shots/c.mp4" --output-dir output/job_42 --mode fit

Replace the paths with actual files each time. No filenames, identity, setting or scene from previous jobs should be assumed.

Personal media is intentionally excluded from git via .gitignore. The project does not require or contain any of the four earlier test videos.

## Limitations / roadmap

Not yet implemented: semantic shot matching; automatic zoom, speed ramp, motion blur or object-based effect detection; full sound design; generative shot completion; general natural-language edit execution; multi-user hosting and human-level creative quality evaluation. The local browser upload/render page and disk-backed project/version storage are implemented.

AGENTS.md contains instructions for further Codex development. WEB_CODEX.md contains practical cloud steps.
