"""Real FFmpeg Smart Reels render, media validation, and measurable FX tests.

All videos and audio are synthetic. NEVER call paid or free external model APIs.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
import cv2

from refeditor.smart_reels import ffprobe_media, render_reels, validate_highlights
from refeditor.transfer_fx import white_edge_bounds, apply_white_panels, apply_reference_flash


class PlanningTests(unittest.TestCase):
    def test_validated_highlights_and_pacing(self):
        response = {"highlights": [
            {"start_s": 3.0, "end_s": 7.0, "reason": "hook"},
            {"start_s": 6.0, "end_s": 10.0, "reason": "duplicate"},
            {"start_s": 10.0, "end_s": 17.0, "reason": "punch line"}
        ]}
        clips = validate_highlights(response, source_duration=20, target_seconds=11)
        self.assertEqual(len(clips), 2)
        self.assertAlmostEqual(sum(x["duration_s"] for x in clips), 11.0)
        self.assertEqual(clips[0]["start_s"], 3.0)

    def test_rejects_hallucinated_or_tiny_highlights(self):
        with self.assertRaises(ValueError):
            validate_highlights({"highlights": [
                {"start_s": -9, "end_s": 14},
                {"start_s": 4000, "end_s": 5000},
                {"start_s": 2, "end_s": 2.2}
            ]}, source_duration=30, target_seconds=10)


class FXTests(unittest.TestCase):
    def test_white_doors_measured_and_rendered(self):
        ref = np.full((140, 220, 3), (35, 90, 170), dtype=np.uint8)
        ref[:, :40] = 255
        ref[:, 183:] = 255
        bounds = white_edge_bounds(ref)
        self.assertGreater(bounds[0], .12)
        self.assertLess(bounds[1], .90)
        subject = np.full_like(ref, (55, 90, 110))
        effected = apply_white_panels(subject, bounds)
        self.assertEqual(int(effected[30, 4, 0]), 255)
        self.assertEqual(int(effected[30, 110, 0]), 55)
        self.assertEqual(int(effected[30, 215, 0]), 255)

    def test_white_reference_scene_not_mistaken_for_panels(self):
        white = np.full((110, 190, 3), 252, dtype=np.uint8)
        self.assertEqual(white_edge_bounds(white), [0., 1.])

    def test_flash_only_at_reference_frame(self):
        frame = np.full((64, 64, 3), 80, dtype=np.uint8)
        events = [{"frame": 12, "strength": .7}]
        self.assertEqual(int(apply_reference_flash(frame.copy(), 2, events).mean()), 80)
        self.assertGreater(float(apply_reference_flash(frame.copy(), 12, events).mean()), 120)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class SmartRenderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.source = self.root / "video.mp4"
        self.music = self.root / "song.wav"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=s=128x96:r=15:d=8",
            "-f", "lavfi", "-i", "sine=frequency=900:duration=8",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-shortest", str(self.source)
        ], check=True, capture_output=True, timeout=45)
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", "sine=frequency=220:duration=8", "-c:a",
            "pcm_s16le", str(self.music)
        ], check=True, capture_output=True, timeout=45)

    def tearDown(self):
        self.folder.cleanup()

    def test_render_reels_has_multiple_cuts_audio_vertical_output(self):
        plan = {
            "source": str(self.source),
            "clips": [
                {"start_s": .3, "end_s": 2.5, "duration_s": 2.2},
                {"start_s": 4.0, "end_s": 6.3, "duration_s": 2.3}
            ]
        }
        final = self.root / "final.mp4"
        progress = []
        render_reels(plan, final, music=self.music, resolution=(216, 384),
                     progress=lambda pc, note: progress.append(pc))
        self.assertTrue(final.is_file())
        data = ffprobe_media(final)
        self.assertTrue(data["video"])
        self.assertTrue(data["audio"])
        self.assertAlmostEqual(data["duration"], 4.5, delta=.35)
        cap = cv2.VideoCapture(str(final))
        self.assertEqual(round(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), 216)
        self.assertEqual(round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), 384)
        cap.release()
        self.assertGreater(max(progress), 85)


if __name__ == "__main__":
    unittest.main()
