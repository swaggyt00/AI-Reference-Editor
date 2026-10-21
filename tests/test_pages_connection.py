"""Ensure that only the GitHub Pages UI can talk to the Windows loopback API."""
import tempfile
import unittest
from fastapi.testclient import TestClient
from refeditor.web import create_app


PAGE = 'https://swaggyt00.github.io'
OTHER = 'https://attacker.example'


class PagesConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(self.temp.name))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def test_pages_get_cors(self):
        res = self.client.get('/api/health', headers={'Origin': PAGE})
        self.assertIn(res.status_code, [200, 503])
        self.assertEqual(res.headers.get('access-control-allow-origin'), PAGE)
        self.assertEqual(res.headers.get('cache-control'), 'no-store')

    def test_pages_preflight_for_upload(self):
        res = self.client.options('/api/projects', headers={
            'Origin': PAGE,
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'x-refeditor-client,content-type',
            'Access-Control-Request-Private-Network': 'true'
        })
        self.assertEqual(res.status_code, 204)
        self.assertEqual(res.headers['access-control-allow-origin'], PAGE)
        self.assertEqual(res.headers['access-control-allow-private-network'], 'true')

    def test_pages_can_create_project_after_permission(self):
        res = self.client.post('/api/projects', headers={
            'Origin': PAGE, 'Sec-Fetch-Site': 'cross-site',
            'X-Refeditor-Client': 'web'
        })
        self.assertEqual(res.status_code, 201, res.text)
        self.assertRegex(res.json()['id'], r'^[a-f0-9]{32}$')
        self.assertEqual(res.headers['access-control-allow-origin'], PAGE)

    def test_reject_non_github_origin(self):
        res = self.client.post('/api/projects', headers={
            'Origin': OTHER, 'Sec-Fetch-Site': 'cross-site',
            'X-Refeditor-Client': 'web'
        })
        self.assertEqual(res.status_code, 403)
        self.assertNotIn('access-control-allow-origin', res.headers)

    def test_reject_other_origin_preflight(self):
        res = self.client.options('/api/projects', headers={
            'Origin': OTHER, 'Access-Control-Request-Method': 'POST'
        })
        self.assertEqual(res.status_code, 403)

    def test_reject_pages_post_without_custom_header(self):
        res = self.client.post('/api/projects', headers={
            'Origin': PAGE, 'Sec-Fetch-Site': 'cross-site'
        })
        self.assertEqual(res.status_code, 403)

    def test_local_interface_unchanged(self):
        res = self.client.post('/api/projects',
                               headers={'X-Refeditor-Client': 'web'})
        self.assertEqual(res.status_code, 201)


if __name__ == '__main__':
    unittest.main()
