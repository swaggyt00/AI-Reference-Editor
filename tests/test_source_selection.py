"""Source assignment must respect evidence, not the last uploaded file."""
import unittest
from refeditor.project import assign_source_to_scene


class SelectionTests(unittest.TestCase):
    def setUp(self):
        # User deliberately uploads street footage before indoor footage.
        self.sources = [{'duration': 3.933}, {'duration': 9.233}]
        self.matches = [
            {'reference_offset_s': 9.088, 'score': .6653},
            {'reference_offset_s': .0417, 'score': .4956},
        ]

    def test_reversed_upload_order_matched_by_original_sound(self):
        self.assertEqual(assign_source_to_scene(0, 9.25, self.sources, self.matches, 0)[0], 1)
        self.assertEqual(assign_source_to_scene(9.25, 15.125, self.sources, self.matches, 1)[0], 0)

    def test_interior_scene_reused_if_reference_has_two_early_shots(self):
        self.assertEqual(assign_source_to_scene(0, 4.875, self.sources, self.matches, 0)[0], 1)
        self.assertEqual(assign_source_to_scene(4.875, 9.0416, self.sources, self.matches, 1)[0], 1)

    def test_no_matching_audio_preserves_user_order(self):
        self.assertEqual(assign_source_to_scene(0, 5, self.sources, [None,None], 0)[0], 0)
        self.assertEqual(assign_source_to_scene(5, 10, self.sources, [None,None], 1)[0], 1)

    def test_ambiguous_audio_preserves_user_order(self):
        ambiguous = [
            {'reference_offset_s': 0, 'score': .55},
            {'reference_offset_s': 0, 'score': .55},
        ]
        self.assertEqual(assign_source_to_scene(0, 3, self.sources, ambiguous, 1)[0], 1)

    def test_low_confidence_is_not_used(self):
        weak=[{'reference_offset_s': 0, 'score': .15},None]
        self.assertEqual(assign_source_to_scene(0, 3, self.sources, weak, 1)[0], 1)


if __name__ == '__main__':
    unittest.main()
