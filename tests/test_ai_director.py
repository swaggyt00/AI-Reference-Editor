"""Offline unit tests: AI matching never requires live API or user's video."""
import copy
import unittest
from unittest.mock import patch

from refeditor.ai_director import validate_matches, apply_validated_matches, validate_budget


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "segments": [
                {"start_frame": 0, "end_frame": 60, "source_index": 0,
                 "source_selection": "user source order", "source_start": 0.0, "source_end": 10.0},
                {"start_frame": 60, "end_frame": 120, "source_index": 1,
                 "source_selection": "user source order", "source_start": 0.0, "source_end": 10.0}
            ],
            "source_files": ["clip-a.mp4", "clip-b.mp4"]
        }

    def test_source_matching_can_correct_upload_order(self):
        proposals = {"matches": [
            {"shot_index": 0, "source_index": 1, "source_start_s": 1.0,
             "confidence": 0.92, "reason": "interior location and movement"},
            {"shot_index": 1, "source_index": 0, "source_start_s": 0.5,
             "confidence": 0.85, "reason": "outdoor run"}
        ]}
        matches = validate_matches(proposals, self.project, [10, 10])
        with patch("refeditor.ai_director.video_metadata", return_value={"duration": 10}):
            applied = apply_validated_matches(self.project, matches)
        self.assertEqual(len(applied), 2)
        self.assertEqual([x["source_index"] for x in self.project["segments"]], [1, 0])
        self.assertEqual(self.project["segments"][0]["source_start"], 1.0)

    def test_invalid_or_low_confidence_matches_ignored(self):
        entries = [
            {"shot_index": 0, "source_index": 2, "source_start_s": 0, "confidence": 1},
            {"shot_index": 1, "source_index": 0, "source_start_s": 9, "confidence": .4},
            {"shot_index": True, "source_index": 0, "source_start_s": 1, "confidence": .9},
            {"shot_index": 0, "source_index": 1, "source_start_s": 1000, "confidence": .99}
        ]
        self.assertEqual(validate_matches({"matches": entries}, self.project, [10, 10]), [])

    def test_shared_audio_not_overridden(self):
        self.project["segments"][0]["source_selection"] = "shared audio @ reference 1s"
        m = {"shot_index": 0, "source_index": 1, "source_start_s": 0,
             "confidence": .95, "reason": "AI thinks so"}
        with patch("refeditor.ai_director.video_metadata", return_value={"duration": 10}):
            applied = apply_validated_matches(self.project, [m])
        self.assertFalse(applied)
        self.assertEqual(self.project["segments"][0]["source_index"], 0)

    def test_pilot_budgets_enforced_before_api_calls(self):
        with patch("refeditor.ai_director.video_metadata", return_value={"duration": 10}):
            self.assertTrue(validate_budget("r.mp4", ["a.mp4", "b.mp4"], self.project["segments"]))
            with self.assertRaises(ValueError):
                validate_budget("r.mp4", ["a", "b", "c", "d"], self.project["segments"])
        with patch("refeditor.ai_director.video_metadata", return_value={"duration": 61}):
            with self.assertRaises(ValueError):
                validate_budget("r.mp4", ["a.mp4"], self.project["segments"])


if __name__ == "__main__":
    unittest.main()
