"""Offline AI Director integration tests: no Gemini API calls or video uploads."""
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from refeditor.ai_director import run_ai_scene_matching


class DirectorGraphicsTest(unittest.TestCase):
    def test_visual_evidence_and_clean_graphic_assets_reach_motion_plan(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            storyboard=root/'board.jpg'
            storyboard.write_bytes(b'fake-small-jpeg-for-mocked-model')
            project={
                'reference':'ref.mp4','source_files':['source.mp4'],
                'motion_design':True,'duration':2.0,'fps':10,
                'reference_analysis':{'hard_cuts':[]},
                'segments':[{'start_frame':0,'end_frame':20,'source_index':0,
                             'source_selection':'user source order','source_start':0,
                             'source_end':2}],
                'warnings':[]
            }
            proposal={
                'matches':[],
                'motion_layers':[
                    {'kind':'title','text':'ON SCREEN','start':0.1,'end':1.5,
                     'observed_tile':0,'confidence':.94},
                    {'kind':'title','text':'HALLUCINATED','start':0.1,'end':1.5,
                     'observed_tile':50,'confidence':.95},
                ],
                'graphic_crops':[],
                'observed_effects':[],
                'limitations':[]
            }
            fake=MagicMock()
            fake.models.generate_content.return_value.text=json.dumps(proposal)
            google=types.ModuleType('google')
            genai=types.ModuleType('google.genai')
            genai.types=types.SimpleNamespace(Part=types.SimpleNamespace(
                from_bytes=lambda **kwargs:kwargs))
            google.genai=genai
            reference_data={'analysis':{'summary':'example'}}
            with patch.dict('sys.modules', {'google':google,'google.genai':genai}), \
                 patch('refeditor.ai_director.validate_budget',return_value=True), \
                 patch('refeditor.ai_director._get_or_analyze',return_value=reference_data), \
                 patch('refeditor.ai_director.video_metadata',return_value={'duration':2}), \
                 patch('refeditor.ai_director.get_client',return_value=fake), \
                 patch('refeditor.reference_storyboard.generate_storyboards',
                       return_value=([storyboard],{'reference_frames':[{'tile':0,'time_s':.5}]})), \
                 patch('refeditor.graphic_reconstruction.extract_reference_graphics',
                       return_value={'layers':[],'assets':{},'extracted':[],'rejected':[]}), \
                 patch('refeditor.graphic_reconstruction.save_graphic_report',
                       return_value={'count':0}):
                plan=run_ai_scene_matching(project,'ref.mp4',['source.mp4'],root,
                                            graphics_dir=root/'graphics')
            self.assertEqual(plan['storyboard_sheets'],1)
            self.assertEqual(plan['motion_layers_validated'],1)
            self.assertEqual(project['motion_layers'][0]['text'],'ON SCREEN')
            sent=fake.models.generate_content.call_args.kwargs['contents']
            self.assertIsInstance(sent,list)
            self.assertEqual(len(sent),2)
            self.assertEqual(sent[1]['mime_type'],'image/jpeg')


if __name__=='__main__':
    unittest.main()
