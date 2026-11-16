import importlib.util
import unittest
import os
from unittest.mock import patch
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('pwa_server', ROOT / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

class PWATests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"APP_PASSWORD":"test-password-12345", "SESSION_SECRET":"test-secret-never-use-in-production-12345"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_public_assets_and_auth_boundary(self):
        with TestClient(server.app, base_url='https://testserver') as client:
            for name, media in server.PWA_TYPES.items():
                response = client.get('/' + name)
                self.assertEqual(response.status_code, 200, name)
                self.assertTrue(response.headers['content-type'].startswith(media))
            self.assertEqual(client.get('/', follow_redirects=False).status_code, 303)
            self.assertEqual(client.get('/api/stats').status_code, 401)
            self.assertEqual(client.get('/server.py').status_code, 404)
            self.assertEqual(client.get('/sw.js').headers['service-worker-allowed'], '/')
            self.assertEqual(client.get('/sw.js').headers['cache-control'], 'no-store')

    def test_install_metadata(self):
        with TestClient(server.app, base_url='https://testserver') as client:
            manifest = client.get('/manifest.webmanifest').json()
            self.assertEqual(manifest['display'], 'standalone')
            self.assertEqual(manifest['scope'], '/')
            self.assertEqual(manifest['start_url'], '/')
            for icon in manifest['icons']:
                with Image.open(ROOT / 'pwa' / icon['src'].lstrip('/')) as im:
                    self.assertEqual(icon['sizes'], f'{im.width}x{im.height}')
            self.assertIn('rel="manifest"', server.LOGIN)
            self.assertIn('src="/pwa.js"', server.LOGIN)

if __name__ == '__main__': unittest.main()
