"""Offline regression tests: simulate Google HTTPX disconnections without API keys."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import httpx

from refeditor.ai_gemini import analyze_video, safe_error_reason
from refeditor.ai_resilience import (
    GeminiStepFailure, call_with_overload_retry, is_transient_network_error,
    retry_label, status_code
)


class NetworkRecoveryTests(unittest.TestCase):
    def test_remote_disconnect_then_success_is_bounded(self):
        calls, sleeps, updates = [], [], []
        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise httpx.RemoteProtocolError('server disconnected without response')
            return {'ok':True}
        result = call_with_overload_retry(
            flaky, sleep=sleeps.append, jitter=lambda a,b:0,
            on_retry=lambda attempt, label:updates.append((attempt,label))
        )
        self.assertEqual(result,{'ok':True})
        self.assertEqual(len(calls),3)
        self.assertEqual(sleeps,[1.5,3.0])
        self.assertEqual(updates,[(1,'network'),(2,'network')])
        self.assertEqual(retry_label('network'),'обрыв сети')

    def test_transport_errors_exhaust_and_network_message_is_correct(self):
        calls=[]
        def broken():
            calls.append(1)
            raise httpx.RemoteProtocolError('private network details')
        with self.assertRaises(httpx.RemoteProtocolError) as error:
            call_with_overload_retry(broken, sleep=lambda x:None,jitter=lambda a,b:0)
        self.assertEqual(len(calls),3)
        user_message=safe_error_reason(error.exception)
        self.assertIn('RemoteProtocolError',user_message)
        self.assertIn('не ошибка API-ключа',user_message)
        self.assertNotIn('private network details',user_message)

    def test_network_timeout_is_retried_but_client_protocol_error_is_not(self):
        self.assertTrue(is_transient_network_error(httpx.ReadTimeout('timeout')))
        self.assertTrue(is_transient_network_error(httpx.ConnectError('disconnect')))
        self.assertFalse(is_transient_network_error(httpx.LocalProtocolError('invalid')))
        count=[]
        def bad_request():
            count.append(1)
            raise httpx.LocalProtocolError('programming error')
        with self.assertRaises(httpx.LocalProtocolError):
            call_with_overload_retry(bad_request,sleep=lambda x:None)
        self.assertEqual(len(count),1)

    def test_http_429_and_403_still_not_retried(self):
        for code in [401,403,429]:
            attempts=[]
            class HttpFailure(Exception):
                def __init__(self, status):
                    self.code=status
            def fail():
                attempts.append(1)
                raise HttpFailure(code)
            with self.assertRaises(HttpFailure):
                call_with_overload_retry(fail,sleep=lambda s:None)
            self.assertEqual(attempts,[1])

    def test_stage_wrap_keeps_original_http_status(self):
        class HttpFailure(Exception):
            code=503
        try:
            try:
                raise HttpFailure('private')
            except HttpFailure as error:
                raise GeminiStepFailure('построение монтажного плана') from error
        except GeminiStepFailure as error:
            self.assertEqual(status_code(error),503)
            reason=safe_error_reason(error)
            self.assertIn('построение монтажного плана',reason)
            self.assertIn('HTTP 503',reason)
            self.assertNotIn('private',reason)

    def test_video_upload_disconnect_does_not_duplicate_remote_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.media'
            source.write_bytes(b'fake placeholder, never decoded')
            fake=MagicMock()
            fake.files.upload.side_effect=httpx.RemoteProtocolError('upload failed')
            with patch('refeditor.ai_gemini.get_client',return_value=fake), \
                 patch('refeditor.ai_gemini._encode_preview',side_effect=lambda src,dst:dst):
                with self.assertRaises(GeminiStepFailure) as err:
                    analyze_video(source,Path(folder)/'output.json',
                                  confirm_external_upload=True)
            self.assertEqual(fake.files.upload.call_count,1)
            self.assertIn('отправка сжатого видео', safe_error_reason(err.exception))
            self.assertIn('RemoteProtocolError',safe_error_reason(err.exception))
            self.assertEqual(fake.files.delete.call_count,0)
            self.assertTrue(fake.close.called)


if __name__=='__main__':
    unittest.main()
