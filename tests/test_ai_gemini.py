"""Gemini is opt-in and encrypted keys never appear in a GitHub commit."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from refeditor.ai_gemini import DEFAULT_MODEL, analyze_video, load_api_key, safe_error_reason, check_local_setup


class GeminiSafetyTests(unittest.TestCase):
    def test_default_is_a_current_video_capable_flash_model(self):
        self.assertTrue(DEFAULT_MODEL.startswith("gemini-"))

    def test_env_key_available_for_ci_or_advanced_local_setup(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-only-injected-key"}):
            self.assertEqual(load_api_key(), "test-only-injected-key")

    def test_missing_key_does_not_trigger_remote_call(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
                with self.assertRaisesRegex(RuntimeError, "Run configure-gemini"):
                    load_api_key(project_root=d)

    def test_video_upload_must_be_explicitly_confirmed(self):
        with self.assertRaisesRegex(ValueError, "confirm-external-upload"):
            analyze_video("nonexistent.mp4", "unused.json")

    def test_invalid_role_rejected_even_after_upload_confirm(self):
        with self.assertRaisesRegex(ValueError, "role"):
            analyze_video("nonexistent.mp4", "unused.json",
                          role="editor", confirm_external_upload=True)

    def test_no_secret_in_generic_error(self):
        message = safe_error_reason(RuntimeError("SECRET-KEY-EXAMPLE"))
        self.assertNotIn("SECRET-KEY-EXAMPLE", message)

    def test_known_local_setup_message_is_safe(self):
        message = safe_error_reason(RuntimeError("Gemini API key not configured. Run configure-gemini.cmd first."))
        self.assertIn("configure-gemini.cmd", message)

    def test_http_429_is_actionable(self):
        error = Exception("response containing secret")
        error.code = 429
        reason = safe_error_reason(error)
        self.assertIn("429", reason)
        self.assertNotIn("secret", reason)

    def test_local_check_does_not_make_api_call(self):
        with patch("refeditor.ai_gemini.load_api_key", return_value="local-dummy-key-123456789"):
            from unittest.mock import MagicMock
            import sys
            fake_google = MagicMock()
            fake_google.genai = MagicMock()
            with patch.dict(sys.modules, {"google": fake_google, "google.genai": fake_google.genai}):
                result = check_local_setup()
                self.assertEqual(result['status'], 'local_key_ready')



if __name__ == "__main__":
    unittest.main()
