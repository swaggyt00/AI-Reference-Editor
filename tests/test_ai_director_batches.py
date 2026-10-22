"""Gemini batching tests: all AI requests mocked, no key or uploads needed."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from refeditor.ai_director import run_ai_scene_matching, validate_budget


class MultiSourceBatchTest(unittest.TestCase):
    def project(self, count):
        return {
            'source_files': [f'/mock/source{i}.mp4' for i in range(count)],
            'duration': 4, 'fps': 10, 'motion_design': False,
            'segments': [
                {'start_frame': 0, 'end_frame': 20, 'source_index': 0,
                 'source_selection':'user source order','source_start':0,
                 'source_end':20},
                {'start_frame': 20, 'end_frame': 40, 'source_index': 1,
                 'source_selection':'user source order','source_start':0,
                 'source_end':20}
            ],
            'reference_analysis':{},'warnings':[]
        }

    def run_mock(self, count, proposals):
        project=self.project(count)
        fake=MagicMock()
        fake.models.generate_content.side_effect=[
            type('Response', (), {'text':json.dumps(item)})() for item in proposals
        ]
        with tempfile.TemporaryDirectory() as folder, \
             patch('refeditor.ai_director.get_client',return_value=fake), \
             patch('refeditor.ai_director.video_metadata',return_value={'duration':20}), \
             patch('refeditor.ai_director._get_or_analyze',
                   return_value={'analysis':{'summary':'mock analysis'}}):
            plan=run_ai_scene_matching(project,'/mock/reference.mp4',
                                        project['source_files'],Path(folder))
        self.assertEqual(fake.models.generate_content.call_count,len(proposals))
        return project,plan,fake

    def test_eight_sources_match_across_two_batches(self):
        project,plan,client=self.run_mock(8,[
            {'matches':[{'shot_index':0,'source_index':5,'source_start_s':1,
                         'confidence':.75,'reason':'first group'},
                        {'shot_index':1,'source_index':1,'source_start_s':2,
                         'confidence':.85,'reason':'first group'}]},
            {'matches':[{'shot_index':0,'source_index':0,'source_start_s':3,
                         'confidence':.96,'reason':'second group'},
                        {'shot_index':1,'source_index':1,'source_start_s':3,
                         'confidence':.50,'reason':'uncertain'},
                        {'shot_index':1,'source_index':7,'source_start_s':3,
                         'confidence':1.0,'reason':'invalid local index'}]}
        ])
        self.assertEqual(plan['sources_analyzed'],8)
        self.assertEqual(plan['director_batches'],2)
        self.assertEqual(plan['batch_size'],6)
        self.assertEqual(project['segments'][0]['source_index'],6)
        self.assertEqual(project['segments'][1]['source_index'],1)
        self.assertEqual(project['segments'][0]['source_start'],3)
        batches=client.models.generate_content.call_args_list
        context0=json.loads(batches[0].kwargs['contents'].split('DATA:')[-1])
        context1=json.loads(batches[1].kwargs['contents'].split('DATA:')[-1])
        self.assertEqual(len(context0['source_descriptions']),6)
        self.assertEqual(len(context1['source_descriptions']),2)
        self.assertEqual([i['source_index'] for i in context1['source_descriptions']],[0,1])

    def test_full_32_source_capacity_and_six_batches(self):
        proposal={'matches':[]}
        project,plan,client=self.run_mock(32,[proposal]*6)
        self.assertEqual(plan['director_batches'],6)
        self.assertEqual(plan['sources_analyzed'],32)
        self.assertEqual(client.models.generate_content.call_count,6)

    def test_completed_matching_batch_is_cached_across_next_batch_failure(self):
        import unittest.mock as um
        project1=self.project(8)
        project2=self.project(8)
        first=type('Resp', (), {'text':json.dumps({
            'matches':[{'shot_index':0,'source_index':2,'confidence':.95,
                        'source_start_s':1,'reason':'ok'}]
        })})()
        final=type('Resp', (), {'text':json.dumps({'matches':[]})})()
        failed_client=MagicMock()
        failed_client.models.generate_content.side_effect=[first,RuntimeError('503 mock')]
        success_client=MagicMock()
        success_client.models.generate_content.return_value=final
        fake_data={'analysis':{'summary':'cached scene'}}
        with tempfile.TemporaryDirectory() as folder, \
             patch('refeditor.ai_director.video_metadata',return_value={'duration':20}), \
             patch('refeditor.ai_director._get_or_analyze',return_value=fake_data), \
             patch('refeditor.ai_director.call_with_overload_retry',
                   side_effect=lambda operation,**kwargs:operation()), \
             patch('refeditor.ai_director.get_client',
                   side_effect=[failed_client,success_client]):
            with self.assertRaisesRegex(RuntimeError,'построение монтажного плана, партия 2 из 2'):
                run_ai_scene_matching(project1,'/mock/reference.mp4',
                                       project1['source_files'],Path(folder))
            cache=list(Path(folder).glob('ai-director-batch-*.json'))
            self.assertEqual(len(cache),1)
            plan=run_ai_scene_matching(project2,'/mock/reference.mp4',
                                        project2['source_files'],Path(folder))
            self.assertEqual(success_client.models.generate_content.call_count,1)
            self.assertEqual(plan['director_batches'],2)
            self.assertEqual(project2['segments'][0]['source_index'],2)

    def test_budget_keeps_duration_check_but_removes_three_clip_cap(self):
        with patch('refeditor.ai_director.video_metadata',return_value={'duration':20}):
            self.assertTrue(validate_budget('reference',['clip']*32,[{}]))
            with self.assertRaisesRegex(ValueError,'32'):
                validate_budget('reference',['clip']*33,[{}])

if __name__=='__main__':
    unittest.main()
