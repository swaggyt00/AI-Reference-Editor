"""Motion-layer schema and end-to-end local Remotion + FFmpeg smoke tests.

No Gemini calls or personal media files are needed.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from refeditor.motion import validate_motion_layers, render_motion, motion_engine_status


class SchemaTests(unittest.TestCase):
    def test_filter_invalid_timestamps_and_fake_assets(self):
        layers = [
            {'kind':'title','start':0.3,'end':1.7,'text':'HELLO','confidence':.91,'animation':'rise'},
            {'kind':'image','start':0,'end':2,'asset':'not_uploaded.png','confidence':.99},
            {'kind':'title','start':0,'end':2,'text':'made up','confidence':.2},
            {'kind':'title','start':-1,'end':1,'text':'invalid','confidence':1},
            {'kind':'video','start':1,'end':2,'asset':'clip','confidence':.8,'source_start':.5}
        ]
        valid = validate_motion_layers(layers, duration=3, available_assets=['clip'])
        self.assertEqual([x['kind'] for x in valid], ['title','video'])
        self.assertEqual(valid[1]['source_start'], .5)

    def test_route_points_are_bounded(self):
        okay = validate_motion_layers([{'kind':'route','text':'Route','start':0,
          'end':2,'confidence':.9,'points':[[.2,.8],[.7,.3]]}],3)
        self.assertEqual(len(okay),1)
        wrong = validate_motion_layers([{'kind':'route','text':'Route','start':0,
          'end':2,'confidence':.9,'points':[[.2,.8],[2,.3]]}],3)
        self.assertEqual(wrong,[])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe')
    and motion_engine_status().get('remotion_ready'), 'Remotion/npm and ffmpeg required')
class RenderTests(unittest.TestCase):
    def test_multilayer_mp4_with_audio_preserved(self):
        import cv2
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            base=root/'base.mp4'
            final=root/'final.mp4'
            img=root/'overlay.png'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                'color=c=blue:s=320x568:r=30:d=3','-f','lavfi','-i',
                'sine=frequency=330:duration=3','-c:v','libx264','-preset','ultrafast',
                '-c:a','aac','-shortest',str(base)],capture_output=True,check=True,timeout=60)
            cv2.imwrite(str(img),cv2.merge([
                255*__import__('numpy').ones((64,64),dtype='uint8')
                for _ in range(3)]))
            layers=[
                {'kind':'title','text':'HELLO MOTION','start':.2,'end':2.2,
                 'x':.5,'y':.28,'confidence':.99,'size':36,'animation':'rise'},
                {'kind':'badge','text':'GRAPHICS','start':1,'end':2.8,
                 'x':.5,'y':.72,'confidence':.95,'size':24,'animation':'pop'},
                {'kind':'image','asset':'user-image','start':.5,'end':2.4,
                 'x':.8,'y':.6,'confidence':.99,'width':.2},
                {'kind':'video','asset':'broll','start':.7,'end':1.8,
                 'x':.28,'y':.55,'confidence':.9,'width':.25,'height':.18,
                 'source_start':.2,'animation':'pop'}
            ]
            render_motion(base,layers,final,
                          asset_files={'user-image':img,'broll':base},
                          duration=3,fps=30,width=320,height=568)
            self.assertTrue(final.exists() and final.stat().st_size>1000)
            probe=subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',str(final)],
                capture_output=True,text=True,check=True)
            streams=json.loads(probe.stdout)['streams']
            self.assertTrue(any(s.get('codec_type')=='video' for s in streams))
            self.assertTrue(any(s.get('codec_type')=='audio' for s in streams))
            cap=cv2.VideoCapture(str(final))
            self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),320)
            self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),568)
            cap.set(cv2.CAP_PROP_POS_MSEC,1500)
            ok,frame=cap.read();cap.release()
            self.assertTrue(ok)
            # Synthetic background is blue; a visible overlay changes the center pixels.
            self.assertGreater(int(frame[:,:,1].max()),80)


if __name__ == '__main__':
    unittest.main()
