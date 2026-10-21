# 76-second reference benchmark — multi-layer motion graphics

The original `IMG_5981(3).MP4` was supplied only in the ChatGPT conversation
for inspection. **Do not commit or publish the reference video.** User-supplied
footage belongs on their Windows computer. This document is a reusable benchmark
description, not a recipe hardcoded into the engine.

## Visual acceptance tasks

| Section | What must be understood | Asset requirements |
| --- | --- | --- |
| 00–12s | primary video, scene cuts, intro typography, inserts | original shots + UI/video inserts |
| 13–22s | pixel-art character, animated text, fire/graphic objects | transparent sprites and particle graphics |
| 22–36s | white cards, animated badges, software interface recording | original screen recording + text |
| 36–64s | route graphics, appearing images, composition changes | image assets and route design data |
| 64–76s | promo titles, graphic logo + fade | owned logo asset, original footage |

## Present capabilities (first Remotion milestone)

- Title/caption/badge/card layers with bounded start/end times and rise/pop/slide/fade.
- Relative (0–1) position and layer order; extra images and video inserts.
- Animated **abstract route** graphics, NOT an accurate street map.
- Existing reference cuts, measured masks and some flash transitions.
- Gemini uses uploaded media and descriptions to propose plans; uncertain layers discarded.
- An offline render pipeline that keeps source media and final MP4 on Windows.

## Not yet at acceptance level

- Pixel-art motion extraction, rotoscoping, particles and 3D tracking.
- Rebuilding proprietary UI/After Effects layers from a flattened video.
- Frame-exact text OCR, font recreation and timing of ALL graphics.
- Pixel-accurate map geography (needs actual map data / source design).
- Person-aware picture-in-picture placement and fully automatic B-roll discovery.
- Creative and audio QC beyond encoding/metadata checks.
- A real-Gemini-key 76-second video integration test.

## Future pass/fail benchmark procedure

1. Upload reference to Windows application; supply separately owned inserts and
   audio. Do not automatically download unknown copyrighted stock media.
2. Approve opt-in proxy upload to Gemini (quota may apply).
3. Compare `project.json` timing and validated motion layers against manually
   marked event list. Record false inserts, missed graphics and timing error.
4. Review MP4 at original resolution, both muted and with audio.
5. Iterate **reusable effect handlers**, never special-case reference filenames.

A technical CI green test does **not** mean this creative benchmark is passed.
