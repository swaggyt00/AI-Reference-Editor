"""Explicit, opt-in Gemini video analysis. No cloud upload during routine render.

Only the user-requested video preview is sent to Google's Gemini Files API,
which is then deleted in a finally block. API key stays outside git, local only.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

DEFAULT_MODEL = "gemini-3.8-flash"


def load_api_key(project_root=None):
    """Read from environment or Windows-user-DPAPI encrypted secrets/gemini.key."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        return key
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[1]
    secret = root / "secrets" / "gemini.key"
    if not secret.exists():
        raise RuntimeError("Gemini API key not configured. Run configure-gemini.cmd first.")
    if os.name != "nt":
        raise RuntimeError("Encrypted Gemini key can be unlocked only on the Windows user profile that created it.")
    # Powershell reconstructs DPAPI key for the current user. Do not log stdout.
    quoted = str(secret.resolve()).replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';"
        f"$s = Get-Content -LiteralPath '{quoted}' -Raw | ConvertTo-SecureString;"
        "$p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);"
        "try {[Console]::Out.Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($p))}"
        "finally {[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}"
    )
    command = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False
    )
    if result.returncode:
        raise RuntimeError("Unable to decrypt Gemini key. Use configure-gemini.cmd under the same Windows account.")
    key = result.stdout.decode("utf-8-sig", errors="replace").strip()
    if len(key) < 15:
        raise RuntimeError("The Gemini key is invalid or empty. Run configure-gemini.cmd again.")
    return key


def get_client():
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Optional Gemini dependency is missing. Run: python -m pip install -r requirements-ai.txt"
        ) from exc
    return genai.Client(api_key=load_api_key())


def check_connection(model=DEFAULT_MODEL):
    """One explicit text-only API request; makes no video uploads."""
    client = get_client()
    try:
        result = client.models.generate_content(
            model=model, contents="Reply with exactly: OK"
        )
        if not result.text:
            raise RuntimeError("Model returned an empty response.")
        return {"status": "connected", "model": model, "response": result.text.strip()[:100]}
    finally:
        client.close()


def _encode_preview(source: Path, target: Path):
    """Smaller proxy video preserving audio for qualitative, NOT frame-accurate analysis."""
    args = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?", "-vf",
        "fps=2,scale=640:-2:flags=lanczos", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "27", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(target)
    ]
    process = subprocess.run(args, capture_output=True, timeout=900, check=False)
    if process.returncode or not target.exists() or target.stat().st_size < 100:
        raise RuntimeError("Could not make the Gemini preview MP4: "
                           + process.stderr.decode(errors="replace")[-450:])
    if target.stat().st_size > 250 * 1024 * 1024:
        raise RuntimeError("Video preview exceeds 250MB; split it into shorter pieces.")
    return target


def analyze_video(video, output, *, role="reference", model=DEFAULT_MODEL,
                  confirm_external_upload=False):
    """Semantic notes for later use by editing agents.

    Does NOT alter project timing, source order or effects automatically.
    Model estimates aren't pixel-accurate; actual effect timing stays with OpenCV.
    """
    if not confirm_external_upload:
        raise ValueError("Uploading video to Google requires --confirm-external-upload.")
    if role not in ("reference", "source"):
        raise ValueError("role must be reference or source")
    source = Path(video).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    result_path = Path(output).expanduser().resolve()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    client = get_client()
    remote_file = None
    with tempfile.TemporaryDirectory(prefix="refeditor-gemini-") as temp:
        proxy = _encode_preview(source, Path(temp) / "preview.mp4")
        try:
            remote_file = client.files.upload(file=str(proxy), config={"mime_type": "video/mp4"})
            deadline = time.monotonic() + 240
            while getattr(getattr(remote_file, "state", None), "name", None) == "PROCESSING":
                if time.monotonic() > deadline:
                    raise TimeoutError("Gemini upload processing exceeded 4 minutes.")
                time.sleep(3)
                remote_file = client.files.get(name=remote_file.name)
            state = getattr(getattr(remote_file, "state", None), "name", None)
            if state != "ACTIVE":
                raise RuntimeError(f"Gemini Files API returned state {state!r}.")
            prompt = f"""You are a professional video editor analyzing a {role} video.
Return JSON only, with keys:
- summary: precise factual description
- shots: list of objects with approximate start_s, end_s, location, subjects,
         action, shot_scale, camera_movement, visual_energy
- effect_candidates: list of objects with approximate time_s, type, description,
         confidence (0..1), evidence
- audio: speech_or_music_summary, sound_event_candidates
- editing_notes: short list of potential matching or quality concerns.
You must separate native camera/actor movement from post-production effects.
If unsure, say unknown, do not invent effects or scenes.
Timestamps and effect candidates are approximations, NOT frame-accurate measurements.
Do not propose effects absent from the actual video."""
            response = client.models.generate_content(
                model=model, contents=[remote_file, prompt],
                config={"response_mime_type": "application/json", "temperature": 0.1}
            )
            if not response.text:
                raise RuntimeError("Gemini returned an empty analysis.")
            try:
                data = json.loads(response.text)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Gemini returned invalid JSON.") from exc
            if not isinstance(data, dict):
                raise RuntimeError("Gemini returned unexpected JSON shape.")
            result = {
                "provider": "Google Gemini API", "model": model,
                "video_name": source.name, "role": role,
                "precision": "semantic estimates only; not frame-accurate",
                "analysis": data
            }
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return result_path
        finally:
            if remote_file is not None:
                try:
                    client.files.delete(name=remote_file.name)
                except Exception:
                    # Cleanup failure does not change the video analysis, but should be visible.
                    print("WARNING: Gemini remote video deletion failed; delete it in AI Studio.", flush=True)
            client.close()
