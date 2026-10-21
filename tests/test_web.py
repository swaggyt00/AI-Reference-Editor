"""Real HTTP/FFmpeg workflow with disposable synthetic media, no personal footage."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from fastapi.testclient import TestClient

from refeditor.web import create_app

HEADERS = {'X-Refeditor-Client': 'web'}


def make_video(path, color, *, audio=False):
    cmd = ['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
           f'color=c={color}:s=160x120:r=12:d=2']
    if audio:
        cmd += ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=2']
    cmd += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p']
    if audio:
        cmd += ['-c:a', 'aac', '-shortest']
    subprocess.run(cmd + [str(path)], check=True, capture_output=True)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = tempfile.TemporaryDirectory()
        cls.reference = Path(cls.media.name) / 'arbitrary-reference.mp4'
        cls.source = Path(cls.media.name) / 'unrelated-footage.mp4'
        make_video(cls.reference, 'red', audio=True)
        make_video(cls.source, 'blue')

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.temp.name), max_upload_bytes=1024 * 1024)
        self.client = TestClient(self.app, headers=HEADERS)
        self.client.__enter__()
        response = self.client.post('/api/projects')
        self.assertEqual(response.status_code, 201, response.text)
        self.project_id = response.json()['id']
        self.url = f'/api/projects/{self.project_id}'

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def upload(self, role, path, name=None):
        response = self.client.post(self.url + '/media', params={
            'role': role, 'name': name or path.name}, content=path.read_bytes())
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def prepare(self):
        self.upload('reference', self.reference)
        self.upload('source', self.source, '../../same name.mp4')
        self.upload('source', self.reference, '../../same name.mp4')

    def render(self, **settings):
        response = self.client.post(self.url + '/renders', json=settings)
        self.assertEqual(response.status_code, 202, response.text)
        rid = response.json()['id']
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = self.client.get(self.url).json()
            run = next(r for r in state['renders'] if r['id'] == rid)
            self.assertGreaterEqual(run['progress'], 0)
            self.assertLessEqual(run['progress'], 100)
            if run['status'] in ('completed', 'failed'):
                self.assertEqual(run['status'], 'completed', run)
                return run
            time.sleep(.05)
        self.fail('Render timed out')

    def test_render_preview_download_and_revision_survive_restart(self):
        self.prepare()
        state = self.client.get(self.url).json()
        self.assertEqual(len(state['sources']), 2)
        self.assertNotEqual(state['sources'][0]['id'], state['sources'][1]['id'])
        self.assertEqual(state['sources'][0]['name'], 'same name.mp4')
        first = self.render(brief='Проверка нового материала', audio='reference')
        self.assertEqual(first['progress'], 100)
        video = self.client.get(first['video_url'])
        self.assertEqual(video.status_code, 200)
        self.assertEqual(video.headers['content-type'], 'video/mp4')
        old_hash = hashlib.sha256(video.content).hexdigest()
        partial = self.client.get(first['video_url'], headers={'Range': 'bytes=0-99'})
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(len(partial.content), 100)
        download = self.client.get(first['download_url'])
        self.assertIn('attachment', download.headers['content-disposition'])
        qa = self.client.get(first['qa_url']).json()
        self.assertTrue(qa['audio_present'])
        self.assertAlmostEqual(qa['duration_s'], 2, delta=.1)
        second = self.render(brief='звук: нет\nдлительность: 1\nрежим: native', audio='reference')
        self.assertNotEqual(first['video_url'], second['video_url'])
        qa2 = self.client.get(second['qa_url']).json()
        self.assertFalse(qa2['audio_present'])
        self.assertAlmostEqual(qa2['duration_s'], 1, delta=.1)
        self.assertEqual(old_hash, hashlib.sha256(self.client.get(first['video_url']).content).hexdigest())
        project = self.client.get(second['project_url']).json()
        self.assertEqual(project['brief'], 'звук: нет\nдлительность: 1\nрежим: native')
        self.assertEqual(project['segments'][0]['speed_mode'], 'native')
        with TestClient(create_app(Path(self.temp.name)), headers=HEADERS) as restarted:
            self.assertEqual(len(restarted.get(self.url).json()['renders']), 2)
            self.assertEqual(restarted.get(second['video_url']).status_code, 200)

    def test_selected_ai_model_reaches_director_without_real_gemini_request(self):
        self.prepare()
        with patch('refeditor.ai_director.run_ai_scene_matching') as director:
            run=self.render(ai_semantic=True, gemini_model='gemini-3.8-flash',
                            brief='preserve existing timings')
        self.assertEqual(run['settings']['gemini_model'],'gemini-3.8-flash')
        self.assertEqual(director.call_count,1)
        self.assertEqual(director.call_args.kwargs['model'],'gemini-3.8-flash')
        response=self.client.post(self.url+'/renders',
            json={'ai_semantic':True,'gemini_model':'unknown-model'})
        self.assertEqual(response.status_code,422,response.text)

    def test_reject_invalid_media_missing_inputs_and_bad_settings(self):
        self.assertEqual(self.client.post(self.url + '/renders', json={}).status_code, 400)
        bad = self.client.post(self.url + '/media', params={'role': 'reference', 'name': 'video.mp4'}, content=b'not a video')
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(list(Path(self.temp.name).rglob('*.part')), [])
        self.assertIsNone(self.client.get(self.url).json()['reference'])
        self.prepare()
        for settings in ({'mode': 'invent'}, {'max_seconds': -1}, {'audio': '/etc/passwd'},
                         {'brief': 'длительность: banana'}, {'source_ids': ['../outside']}):
            with self.subTest(settings=settings):
                self.assertIn(self.client.post(self.url + '/renders', json=settings).status_code, (400, 422))

    def test_upload_limit_and_origin_and_artifact_allowlist(self):
        result = self.client.post(self.url + '/media', params={'role': 'source', 'name': 'huge.mp4'}, content=b'x' * (1024 * 1024 + 1))
        self.assertEqual(result.status_code, 413)
        self.assertEqual(list(Path(self.temp.name).rglob('*.part')), [])
        self.assertEqual(self.client.post('/api/projects', headers={'Origin': 'https://evil.example'}).status_code, 403)
        with TestClient(self.app) as no_header:
            self.assertEqual(no_header.post('/api/projects').status_code, 403)
        self.assertEqual(self.client.get(self.url + '/renders/fake/files/project.json').status_code, 404)
        self.assertEqual(self.client.get('/api/projects/not-an-id').status_code, 404)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/api/health').status_code, 200)

    def test_unknown_brief_is_preserved_with_honest_warning(self):
        self.prepare()
        run = self.render(brief='Добавь сложный трекинг и найди человека', audio='none')
        self.assertTrue(any('текст' in w.lower() for w in run['warnings']))
        project = self.client.get(run['project_url']).json()
        self.assertEqual(project['effects'], [])
        self.assertEqual(project['brief'], 'Добавь сложный трекинг и найди человека')

    def test_failure_is_visible_and_retry_keeps_previous_result(self):
        self.prepare()
        first = self.render(audio='none')
        with patch('refeditor.web_jobs.stream_render', side_effect=RuntimeError('encoder failed')):
            with self.assertLogs('refeditor.web_jobs', level='ERROR'):
                response = self.client.post(self.url + '/renders', json={})
                self.assertEqual(response.status_code, 202)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    run = self.client.get(self.url).json()['renders'][-1]
                    if run['status'] == 'failed':
                        break
                    time.sleep(.02)
                self.assertEqual(run['status'], 'failed')
                self.assertTrue(run['error'])
                self.assertEqual(self.client.get(run['video_url']).status_code, 404)
        self.assertEqual(self.client.get(first['video_url']).status_code, 200)
        self.assertEqual(self.render(audio='none')['version'], 3)

    def test_active_render_rejects_duplicate_render_and_upload(self):
        self.prepare()
        entered, release = Event(), Event()
        from refeditor.web_jobs import stream_render

        def waiting_render(*args, **kwargs):
            entered.set()
            release.wait(5)
            return stream_render(*args, **kwargs)

        with patch('refeditor.web_jobs.stream_render', side_effect=waiting_render):
            self.assertEqual(self.client.post(self.url + '/renders', json={}).status_code, 202)
            self.assertTrue(entered.wait(5))
            try:
                self.assertEqual(self.client.post(self.url + '/renders', json={}).status_code, 400)
                result = self.client.post(self.url + '/media', params={'role': 'source', 'name': 'new.mp4'}, content=self.source.read_bytes())
                self.assertEqual(result.status_code, 409)
            finally:
                release.set()

    def test_interrupted_job_becomes_retryable_after_restart(self):
        self.prepare()
        state_file = Path(self.temp.name) / self.project_id / 'state.json'
        state = json.loads(state_file.read_text())
        state['renders'].append({'id': 'a' * 32, 'status': 'running', 'progress': 40})
        state_file.write_text(json.dumps(state))
        with TestClient(create_app(self.temp.name), headers=HEADERS) as client:
            run = client.get(self.url).json()['renders'][0]
            self.assertEqual(run['status'], 'failed')
            self.assertIn('перезапущен', run['error'])

    def test_source_order_controls_actual_pixels(self):
        self.prepare()
        state = self.client.get(self.url).json()
        run = self.render(source_ids=[state['sources'][1]['id'], state['sources'][0]['id']], audio='none')
        import cv2
        path = Path(self.temp.name) / 'sample.mp4'
        path.write_bytes(self.client.get(run['video_url']).content)
        cap = cv2.VideoCapture(str(path))
        try:
            ok, frame = cap.read()
            self.assertTrue(ok)
            # With no shared audio, the first selected source is used for the first shot.
            self.assertGreater(float(frame[:, :, 2].mean()), float(frame[:, :, 0].mean()) + 100)
        finally:
            cap.release()

    def test_duration_limit_preserves_timeline_and_analysis_cache_recovers(self):
        self.prepare()
        full = self.render(audio='none')
        original = self.client.get(full['project_url']).json()
        cache = next((Path(self.temp.name) / self.project_id).glob('analysis-*.json'))
        cache.write_text('{interrupted write')
        short = self.render(audio='none', max_seconds=1)
        trimmed = self.client.get(short['project_url']).json()
        self.assertEqual(original['segments'], trimmed['segments'])
        self.assertEqual(trimmed['duration'], 1)

    def test_cuts_masks_and_distinct_sources_render_at_expected_boundary(self):
        import cv2
        import numpy as np
        path = Path(self.temp.name) / 'new-reference.mkv'
        # Two unlike scenes and real digital side masks, unrelated to old examples.
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'FFV1'), 12, (160, 120))
        self.assertTrue(writer.isOpened())
        for i in range(72):
            frame = np.zeros((120, 160, 3), np.uint8)
            frame[:, 24:136] = (0, 0, 230) if i < 36 else (230, 0, 0)
            writer.write(frame)
        writer.release()
        self.upload('reference', path)
        self.upload('source', self.source)
        self.upload('source', self.reference)
        run = self.render(audio='none')
        qa = self.client.get(run['qa_url']).json()
        self.assertEqual(qa['reference_cuts_s'], [3.0])
        self.assertAlmostEqual(qa['duration_s'], 6, delta=.1)
        self.assertLess(qa['checks']['masked_edge_mean_absolute_error_fraction'], .02)
        rendered = Path(self.temp.name) / 'checked.mp4'
        rendered.write_bytes(self.client.get(run['video_url']).content)
        cap = cv2.VideoCapture(str(rendered))
        try:
            for index, channel in [(35, 0), (36, 2)]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, image = cap.read()
                self.assertTrue(ok)
                self.assertGreater(float(image[:, 40:120, channel].mean()), 200)
                self.assertLess(float(image[:, :20].mean()), 5)
        finally:
            cap.release()

    def test_odd_dimensions_pad_for_browser_h264(self):
        path = Path(self.temp.name) / 'odd.mkv'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc=size=161x121:rate=12:duration=1', '-c:v', 'ffv1', str(path)],
                       check=True, capture_output=True)
        self.upload('reference', path)
        self.upload('source', self.source)
        run = self.render(audio='none')
        qa = self.client.get(run['qa_url']).json()
        self.assertEqual(qa['resolution'], '162x122')

    def test_delete_one_uploaded_file_is_physical_and_replaceable(self):
        self.prepare()
        run = self.render(audio='none')
        state = self.client.get(self.url).json()
        reference_id = state['reference']['id']
        source_id = state['sources'][0]['id']
        file_folder = Path(self.temp.name) / self.project_id / 'media'
        self.assertTrue((file_folder / (reference_id + '.media')).is_file())
        self.assertTrue((file_folder / (source_id + '.media')).is_file())
        deleted = self.client.delete(self.url + '/media/' + source_id)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertFalse((file_folder / (source_id + '.media')).exists())
        self.assertEqual(len(deleted.json()['sources']), 1)
        self.assertEqual(self.client.delete(self.url + '/media/' + source_id).status_code, 404)
        self.assertEqual(self.client.delete(self.url + '/media/../../etc').status_code, 404)
        # Existing rendered versions intentionally remain playable.
        self.assertEqual(self.client.get(run['video_url']).status_code, 200)
        deleted_ref = self.client.delete(self.url + '/media/' + reference_id)
        self.assertEqual(deleted_ref.status_code, 200, deleted_ref.text)
        self.assertIsNone(deleted_ref.json()['reference'])
        self.assertFalse((file_folder / (reference_id + '.media')).exists())
        self.assertEqual(self.upload('reference', self.reference)['name'], self.reference.name)
        self.assertEqual(self.upload('source', self.source)['name'], self.source.name)
        self.assertEqual(len(self.client.get(self.url).json()['sources']), 2)

    def test_delete_music_and_reject_unauthorized_delete(self):
        music = self.upload('music', self.reference)  # has a valid audio track
        local = Path(self.temp.name) / self.project_id / 'media' / (music['id'] + '.media')
        self.assertTrue(local.exists())
        self.assertEqual(self.client.delete(self.url + '/media/' + music['id'],
            headers={'Origin': 'https://evil.example'}).status_code, 403)
        with TestClient(self.app) as no_header:
            self.assertEqual(no_header.delete(self.url + '/media/' + music['id']).status_code, 403)
        self.assertTrue(local.exists())
        result = self.client.delete(self.url + '/media/' + music['id'])
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIsNone(result.json()['music'])
        self.assertFalse(local.exists())

    def test_projects_library_lists_prior_projects_for_site_cleanup(self):
        self.upload('reference', self.reference)
        old_id = self.project_id
        extra = self.client.post('/api/projects')
        self.assertEqual(extra.status_code, 201)
        second_id = extra.json()['id']
        listings = self.client.get('/api/projects')
        self.assertEqual(listings.status_code, 200)
        rows = {p['id']: p for p in listings.json()}
        self.assertIn(old_id, rows)
        self.assertIn(second_id, rows)
        self.assertEqual(rows[old_id]['reference_name'], self.reference.name)
        self.assertEqual(rows[old_id]['sources'], 0)
        self.assertGreater(rows[old_id]['uploaded_bytes'], 0)
        self.assertEqual(rows[second_id]['uploaded_bytes'], 0)
        self.assertNotIn('filesystem_path', rows[old_id])
        self.assertEqual(self.client.delete('/api/projects/' + old_id).status_code, 200)
        remaining = {p['id'] for p in self.client.get('/api/projects').json()}
        self.assertNotIn(old_id, remaining)
        self.assertIn(second_id, remaining)

    def test_delete_entire_project_removes_renders_and_state(self):
        self.prepare()
        run = self.render(audio='none')
        folder = Path(self.temp.name) / self.project_id
        self.assertTrue((folder / 'renders' / run['id'] / 'final.mp4').is_file())
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['deleted'])
        self.assertFalse(folder.exists())
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(run['video_url']).status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 404)
        self.assertEqual(self.client.post('/api/projects').status_code, 201)

    def test_delete_refused_during_render_or_upload(self):
        self.prepare()
        asset = self.client.get(self.url).json()['sources'][0]
        entered, release = Event(), Event()
        from refeditor.web_jobs import stream_render

        def waiting_render(*args, **kwargs):
            entered.set()
            release.wait(7)
            return stream_render(*args, **kwargs)

        with patch('refeditor.web_jobs.stream_render', side_effect=waiting_render):
            response = self.client.post(self.url + '/renders', json={})
            self.assertEqual(response.status_code, 202)
            self.assertTrue(entered.wait(5))
            try:
                self.assertEqual(self.client.delete(self.url).status_code, 409)
                self.assertEqual(self.client.delete(self.url + '/media/' + asset['id']).status_code, 409)
            finally:
                release.set()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if self.client.get(self.url).json()['renders'][-1]['status'] not in ('queued', 'running'):
                break
            time.sleep(.05)
        with self.app.state.store.lock:
            self.app.state.store.uploading.add(self.project_id)
        try:
            self.assertEqual(self.client.delete(self.url).status_code, 409)
            self.assertEqual(self.client.delete(self.url + '/media/' + asset['id']).status_code, 409)
        finally:
            with self.app.state.store.lock:
                self.app.state.store.uploading.discard(self.project_id)
        self.assertEqual(self.client.delete(self.url).status_code, 200)

    def test_upload_retry_is_idempotent_after_response_loss(self):
        upload_id = 'b' * 32
        params = {'role': 'reference', 'name': self.reference.name, 'upload_id': upload_id}
        first = self.client.post(self.url + '/media', params=params, content=self.reference.read_bytes())
        self.assertEqual(first.status_code, 201)
        retried = self.client.post(self.url + '/media', params=params, content=self.reference.read_bytes())
        self.assertEqual(retried.status_code, 201)
        self.assertEqual(first.json(), retried.json())
        self.assertEqual(first.json()['id'], upload_id)
        self.assertEqual(len(list((Path(self.temp.name) / self.project_id / 'media').glob('*.media'))), 1)


if __name__ == '__main__':
    unittest.main()
