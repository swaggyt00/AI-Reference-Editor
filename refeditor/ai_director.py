"""Opt-in Gemini scene matching with hard limits and deterministic validation.

First preview AI feature: chooses correct source scene and source starting moment.
The model does NOT invent or execute visual effects. All private footage stays
local unless the user explicitly enables AI mode for the current render.
"""
from __future__ import annotations

import json
from pathlib import Path
import hashlib

from .ai_gemini import DEFAULT_MODEL, analyze_video, get_client
from .analyzer import video_metadata

AI_MAX_SOURCES = 3
AI_MAX_CLIP_SECONDS = 60
AI_MAX_SCENES = 12
AI_MIN_CONFIDENCE = .65


def validate_budget(reference, sources, segments):
    """Protect free-tier users against accidental excessive API usage."""
    if not (1 <= len(sources) <= AI_MAX_SOURCES):
        raise ValueError("AI pilot supports up to three source videos per render.")
    if len(segments) > AI_MAX_SCENES:
        raise ValueError("AI pilot supports up to twelve reference shots.")
    for file in [reference, *sources]:
        if video_metadata(file)["duration"] > AI_MAX_CLIP_SECONDS:
            raise ValueError("AI pilot accepts videos of at most 60 seconds each.")
    return True


def _summary(data):
    """Keep Gemini output bounded before passing it back into another prompt."""
    analysis = data.get("analysis")
    if not isinstance(analysis, dict):
        return {}
    result = {}
    for name in ("summary", "shots", "effect_candidates", "audio", "editing_notes"):
        value = analysis.get(name)
        if isinstance(value, str):
            result[name] = value[:1800]
        elif isinstance(value, list):
            result[name] = value[:35]
        elif isinstance(value, dict):
            result[name] = value
    return result


def _get_or_analyze(file, cache, role, model):
    cache = Path(cache)
    if cache.is_file():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data["model"] == model and data["role"] == role:
                return data
        except (ValueError, KeyError, OSError):
            pass
    analyze_video(file, cache, role=role, model=model, confirm_external_upload=True)
    return json.loads(cache.read_text(encoding="utf-8"))


def validate_matches(response, project, source_durations):
    """Reject invented indices, untrusted timestamps, and uncertain matches."""
    shots = project["segments"]
    found = set()
    applied = []
    for match in response.get("matches", []) if isinstance(response, dict) else []:
        if not isinstance(match, dict):
            continue
        try:
            idx = match["shot_index"]
            src = match["source_index"]
            conf = float(match["confidence"])
            t = float(match.get("source_start_s", 0))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        # Reject booleans as indices: bool subclasses int in Python.
        if type(idx) is not int or type(src) is not int:
            continue
        if idx in found or idx not in range(len(shots)) or src not in range(len(source_durations)):
            continue
        if not (AI_MIN_CONFIDENCE <= conf <= 1.0) or not (0 <= t < source_durations[src]):
            continue
        found.add(idx)
        reason = str(match.get("reason", ""))[:220]
        applied.append({"shot_index": idx, "source_index": src,
                        "source_start_s": t, "confidence": conf, "reason": reason})
    return applied


def apply_validated_matches(project, matches):
    changes = []
    for m in matches:
        segment = project["segments"][m["shot_index"]]
        # Preserve stronger time-aligned evidence where possible.
        if segment.get("source_selection", "").startswith("shared audio"):
            continue
        segment["source_index"] = m["source_index"]
        segment["source_start"] = m["source_start_s"]
        segment["source_end"] = video_metadata(
            project["source_files"][m["source_index"]])["duration"]
        segment["source_selection"] = (
            f"Gemini semantic match ({m['confidence']:.2f}): {m['reason']}"
        )
        changes.append(m)
    return changes


def run_ai_scene_matching(project, reference_path, source_paths, cache_dir, *,
                          model=DEFAULT_MODEL, progress=None):
    """Uploads compressed proxies to Google ONLY for user-opted-in AI render.

    One model call per uncached uploaded video + one text-only director call.
    Models may have quotas, so abort rather than silently falling back.
    """
    validate_budget(reference_path, source_paths, project["segments"])
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if progress:
        progress("Gemini: анализ референса", 33)
    ref_data = _get_or_analyze(
        reference_path, cache_dir / "ai-reference.json", "reference", model
    )
    sources_data = []
    for idx, src in enumerate(source_paths):
        if progress:
            progress(f"Gemini: анализ исходника {idx+1}/{len(source_paths)}", 33 + int(3*(idx+1)/len(source_paths)))
        media_key = hashlib.sha256(str(Path(src).resolve()).encode("utf-8")).hexdigest()[:18]
        data = _get_or_analyze(
            src, cache_dir / f"ai-source-{media_key}.json", "source", model
        )
        sources_data.append(data)
    source_durations = [video_metadata(s)["duration"] for s in source_paths]
    # The shot windows are measured by OpenCV; descriptions are approximate.
    boundaries = [
        {"shot_index": idx,
         "start_s": round(seg["start_frame"] / project["fps"], 3),
         "end_s": round(seg["end_frame"] / project["fps"], 3)}
        for idx, seg in enumerate(project["segments"])
    ]
    context = {
        "reference_shots": boundaries,
        "reference_description": _summary(ref_data),
        "source_descriptions": [
            {"source_index": idx, "duration_s": source_durations[idx],
             "description": _summary(data)}
            for idx, data in enumerate(sources_data)
        ],
        "task_brief": str(project.get("brief", ""))[:3500],
    }
    prompt = """You are a senior video-editing SOURCE MATCHER, not a video generator.
Given reference shots and descriptions of DIFFERENT source footage, select the
best matching source and SOURCE START TIME for each shot.
Match concrete subjects, actions, locations, poses and camera composition.
Prefer visual evidence to chronological upload order. Do not invent footage.
If none matches convincingly, OMIT that shot rather than guessing.
Reference shot times are authoritative. Source timestamps are approximate.
Respond with a JSON object containing ONLY:
{"matches": [{"shot_index":0,"source_index":0,"source_start_s":0.0,
             "confidence":0.85,"reason":"short description"}],
 "observed_effects": ["effects visible in reference, only if evidenced"],
 "limitations": ["what can't be reproduced with the supplied footage"]}.
The matching confidence is between 0 and 1, under 0.65 means uncertain.
Do not suggest adding generic flashy transitions when absent in the reference.
DATA: """ + json.dumps(context, ensure_ascii=False)
    if progress:
        progress("Gemini: сопоставление сцен", 37)
    client = get_client()
    try:
        response = client.models.generate_content(
            model=model, contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.1}
        )
        if not response.text:
            raise RuntimeError("Gemini returned no edit-plan proposal.")
        proposed = json.loads(response.text)
        if not isinstance(proposed, dict):
            raise ValueError("Gemini edit-plan response must be a JSON object.")
    finally:
        client.close()
    valid = validate_matches(proposed, project, source_durations)
    applied = apply_validated_matches(project, valid)
    observations = proposed.get("observed_effects", [])
    limitations = proposed.get("limitations", [])
    plan = {
        "model": model,
        "semantic_matches_applied": applied,
        "effect_observations": observations[:25] if isinstance(observations, list) else [],
        "limitations": limitations[:25] if isinstance(limitations, list) else [],
        "effect_execution": "NOT enabled: observations require frame-accurate validation"
    }
    project["ai_scene_plan"] = plan
    if not applied:
        project["warnings"].append(
            "Gemini found no high-confidence scene match. Existing source-order/audio alignment was kept."
        )
    else:
        project["warnings"].append(
            f"Gemini matched {len(applied)} reference scenes to source clips; "
            "complex VFX remain unimplemented."
        )
    return plan
