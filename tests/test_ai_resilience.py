"""Offline regression tests for Gemini HTTP 503 recovery and cached progress.

No actual Gemini API requests, credits, keys or user video uploads.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from refeditor.ai_resilience import (
    call_with_overload_retry, status_code, validate_model, SUPPORTED_MODELS
)
from refeditor.ai_director import _get_or_analyze
from refeditor.ai_gemini import safe_error_reason
from refeditor.web import RenderSettings


class FakeApiError(Exception):
    def __init__(self, code):
        super().__init__('hidden internal request details')
        self.code = code


class RetryTests(unittest.TestCase):
    def test_503_recovers_once_and_reports_progress(self):
        attempts = []
        slept = []
        progress = []
        def call():
            attempts.append(1)
            if len(attempts) == 1:
                raise FakeApiError(503)
            return {'result':'good'}
        result = call_with_overload_retry(call, sleep=slept.append,
            jitter=lambda low, high:0.0,
            on_retry=lambda number, status: progress.append((number,status)))
        self.assertEqual(result, {'result':'good'})
        self.assertEqual(len(attempts),2)
        self.assertEqual(len(slept),1)
        self.assertEqual(progress,[(1,503)])

    def test_503_exhausted_is_bounded_and_sanitized(self):
        attempts = []
        def fail():
            attempts.append(1)
            raise FakeApiError('503')
        with self.assertRaises(FakeApiError) as cm:
            call_with_overload_retry(fail,sleep=lambda seconds:None,jitter=lambda a,b:0)
        self.assertEqual(len(attempts),2)
        safe = safe_error_reason(cm.exception)
        self.assertIn('503',safe)
        self.assertNotIn('hidden internal',safe)

    def test_invalid_keys_and_quota_are_never_retried(self):
        for status in (400,401,403,404,429):
            attempts=[]
            def fail():
                attempts.append(1)
                raise FakeApiError(status)
            with self.assertRaises(FakeApiError):
                call_with_overload_retry(fail,sleep=lambda seconds:None)
            self.assertEqual(attempts,[1],status)

    def test_only_retry_transient_server_errors(self):
        for status in (502,503,504):
            attempts=[]
            def request():
                attempts.append(1)
                if len(attempts)==1:
                    raise FakeApiError(status)
                return 'OK'
            self.assertEqual(call_with_overload_retry(request,
                sleep=lambda t:None,jitter=lambda a,b:0),'OK')
            self.assertEqual(len(attempts),2)

    def test_model_field_is_manual_and_strict(self):
        self.assertEqual(RenderSettings().gemini_model,'gemini-3.6-flash')
        self.assertEqual(len(SUPPORTED_MODELS),3)
        for model in SUPPORTED_MODELS:
            self.assertEqual(validate_model(model),model)
            self.assertEqual(RenderSettings(gemini_model=model).gemini_model,model)
        with self.assertRaises(Exception):
            RenderSettings(gemini_model='gemini-paid-custom')
        with self.assertRaises(ValueError):
            validate_model('gemini-paid-custom')

    def test_complete_cached_ai_summary_survives_model_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            video=root/'abc123.media'
            video.write_bytes(b'example mock file')
            cache=root/'analysis.json'
            cache.write_text(json.dumps({
                'model':'gemini-3.6-flash','role':'reference',
                'video_name':video.name, 'analysis':{'summary':'cached already'}
            }))
            with patch('refeditor.ai_director.analyze_video') as analyzer:
                data=_get_or_analyze(video,cache,'reference','gemini-3.8-flash')
            analyzer.assert_not_called()
            self.assertEqual(data['analysis']['summary'],'cached already')

    def test_replaced_upload_cannot_reuse_different_video_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            video=root/'new-file-id.media'
            video.write_bytes(b'new input')
            cache=root/'ai-reference.json'
            cache.write_text(json.dumps({
                'model':'gemini-3.6-flash','role':'reference',
                'video_name':'old-file-id.media','analysis':{'summary':'stale'}
            }))
            def new_analysis(file,cache_path,**kwargs):
                Path(cache_path).write_text(json.dumps({
                    'model':kwargs['model'],'role':kwargs['role'],
                    'video_name':Path(file).name,
                    'analysis':{'summary':'fresh'}
                }))
            with patch('refeditor.ai_director.analyze_video',side_effect=new_analysis) as called:
                data=_get_or_analyze(video,cache,'reference','gemini-3.8-flash')
            self.assertEqual(called.call_count,1)
            self.assertEqual(data['analysis']['summary'],'fresh')


if __name__ == '__main__':
    unittest.main()
