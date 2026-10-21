"""Offline evidence-driven graphic extraction and storyboard regressions."""
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from refeditor.graphic_reconstruction import extract_alpha_asset, extract_reference_graphics
from refeditor.reference_storyboard import storyboard_times, generate_storyboards
from refeditor.motion import validate_motion_layers


class GraphicTests(unittest.TestCase):
    def test_flat_background_graphic_has_real_alpha(self):
        with tempfile.TemporaryDirectory() as folder:
            frame=np.full((180,320,3),235,np.uint8)
            cv2.circle(frame,(160,90),34,(25,60,240),-1)
            path=Path(folder)/'icon.png'
            self.assertIsNotNone(extract_alpha_asset(frame,[.26,.2,.48,.60],path))
            rgba=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
            self.assertEqual(rgba.shape[2],4)
            self.assertEqual(int(rgba[0,0,3]),0)
            self.assertGreater(int(rgba[rgba.shape[0]//2,rgba.shape[1]//2,3]),200)

    def test_does_not_extract_real_world_scene(self):
        rng=np.random.default_rng(8)
        photo=rng.integers(0,256,(180,320,3),dtype=np.uint8)
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(extract_alpha_asset(
                photo,[.1,.1,.65,.65],Path(folder)/'bad.png'))

    def test_graphic_candidate_requires_real_evidence_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);video=root/'reference.mp4'
            writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(320,180))
            for _ in range(20):
                frame=np.full((180,320,3),235,np.uint8)
                cv2.rectangle(frame,(135,75),(186,105),(20,20,240),-1)
                writer.write(frame)
            writer.release()
            candidates=[
                {'category':'sticker','start':0,'end':1.8,
                 'sample_time_s':.5,'box':[.26,.2,.48,.60],
                 'confidence':.98,'animation':'pop'},
                {'category':'sticker','start':0,'end':1.8,
                 'sample_time_s':1.2,'box':[.26,.2,.48,.60],
                 'confidence':.98},
                {'category':'person','start':0,'end':1.8,
                 'sample_time_s':.5,'box':[.26,.2,.48,.60],
                 'confidence':.98}
            ]
            r=extract_reference_graphics(video,candidates,root/'assets',
                    duration=2,allowed_sample_times=[.5])
            self.assertEqual(len(r['extracted']),1,r)
            self.assertEqual(len(r['rejected']),2,r)
            self.assertTrue(Path(r['assets']['ref_graphic_0']).is_file())
            self.assertEqual(r['layers'][0]['kind'],'image')

    def test_bounded_storyboard_and_animation_track(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);video=root/'clip.mp4'
            writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(320,180))
            for i in range(24):
                writer.write(np.full((180,320,3),(20+i*4,35,80),np.uint8))
            writer.release()
            sheets,index=generate_storyboards(video,root/'boards',max_frames=12)
            self.assertTrue(sheets and sheets[0].is_file())
            self.assertLessEqual(len(index['reference_frames']),12)
            self.assertLessEqual(len(storyboard_times(76,[{'time':20}],max_frames=48)),48)
        layer={'kind':'title','text':'VISIBLE', 'start':1,'end':4,
               'confidence':.96,'observed_tile':3,'track':[
                   {'time':1,'x':.3,'y':.6,'scale':.8},
                   {'time':2,'x':.5,'y':.5,'scale':1.0}
               ]}
        valid=validate_motion_layers([layer],5)
        self.assertEqual(len(valid[0]['track']),2)
        bad=layer|{'track':[{'time':1,'x':20,'y':.5},
                           {'time':2,'x':.5,'y':.5}]}
        self.assertNotIn('track',validate_motion_layers([bad],5)[0])

class TemporalGraphicTests(unittest.TestCase):
    def test_pixel_sprite_over_static_textured_background(self):
        from refeditor.graphic_reconstruction import extract_temporal_asset
        rng=np.random.default_rng(10)
        background=rng.integers(20,140,(180,320,3),dtype=np.uint8)
        foreground=background.copy()
        cv2.rectangle(foreground,(135,73),(181,108),(255,255,0),-1)
        with tempfile.TemporaryDirectory() as d:
            result=extract_temporal_asset(
                foreground,background,[.28,.22,.45,.57],Path(d)/'sprite.png')
            self.assertIsNotNone(result)
            self.assertEqual(result['extraction'],'temporal_static_plate')
            self.assertTrue((Path(d)/'sprite.png').is_file())

    def test_moving_camera_does_not_become_a_sticker(self):
        from refeditor.graphic_reconstruction import extract_temporal_asset
        rng=np.random.default_rng(10)
        background=rng.integers(20,140,(180,320,3),dtype=np.uint8)
        moving=np.roll(background,9,axis=1)
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(extract_temporal_asset(
                moving,background,[.28,.22,.45,.57],Path(d)/'sprite.png'))


if __name__=='__main__':
    unittest.main()
