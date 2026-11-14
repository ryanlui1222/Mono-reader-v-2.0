import importlib.util
import os
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location('monoreader_server', Path(__file__).with_name('server.py'))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'APP_PASSWORD': 'test-only-password-123', 'SESSION_SECRET': 'test-only-signing-key-never-deploy-this-value'})
        self.env.start()
        server.failures.clear()
        self.client = TestClient(server.app, base_url='https://testserver')

    def tearDown(self):
        self.env.stop()
        self.client.close()

    def login(self):
        return self.client.post('/login', data={'password': 'test-only-password-123'}, follow_redirects=False)

    def test_authentication_and_cookie(self):
        self.assertEqual(self.client.get('/api/table/articles').status_code, 401)
        self.assertEqual(self.client.post('/login', data={'password': 'wrong'}).status_code, 401)
        res = self.login()
        self.assertEqual(res.status_code, 303)
        self.assertIn('HttpOnly', res.headers['set-cookie'])
        self.assertIn('Secure', res.headers['set-cookie'])
        self.assertEqual(self.client.get('/').status_code, 200)
        self.client.post('/logout', follow_redirects=False)
        self.assertEqual(self.client.get('/api/table/articles').status_code, 401)

    def test_fail_closed_and_origin(self):
        with patch.dict(os.environ, {'APP_PASSWORD': ''}):
            self.assertEqual(self.client.get('/').status_code, 503)
        self.assertEqual(self.client.post('/login', headers={'origin': 'https://other.example'}, data={'password':'x'}).status_code,403)

    def test_queries_and_limits(self):
        connection = sqlite3.connect(':memory:', check_same_thread=False)
        connection.execute('CREATE TABLE articles (Link TEXT PRIMARY KEY, Title TEXT, SortDate TEXT)')
        connection.executemany('INSERT INTO articles VALUES (?,?,?)', [(f'https://example.test/{i}',f'Article {i}','2026-11-14') for i in range(501)])
        queries=[]
        async def query(sql):
            queries.append(sql)
            cur=connection.execute(sql)
            cols=[d[0] for d in cur.description]
            return cols,[dict(zip(cols,r)) for r in cur.fetchall()]
        self.login()
        with patch.object(server,'query',query):
            data=self.client.get('/api/table/articles?offset=0').json()
            self.assertEqual(len(data['rows']),50)
            self.assertEqual(data['total'],501)
            self.assertEqual(data['next_offset'],50)
            self.assertTrue(data['truncated'])
            self.assertIsNone(self.client.get('/api/table/articles?offset=450').json()['next_offset'])
            self.assertTrue(self.client.get('/api/table/omni_vault').json()['missing'])
            self.assertEqual(self.client.get('/api/table/sqlite_master').status_code,400)
            self.assertEqual(self.client.get('/api/table/articles?offset=500').status_code,400)
            self.assertEqual(self.client.post('/api/table/articles',json={'title':'change'}).status_code,405)
        self.assertTrue(all(q.startswith('SELECT ') for q in queries))
        self.assertEqual(connection.execute('SELECT COUNT(*) FROM articles').fetchone()[0],501)
        connection.close()

    def test_decoder_and_url(self):
        columns,rows=server.decode_result({'results':[{'type':'ok','response':{'result':{'cols':[{'name':'id'},{'name':'note'}],'rows':[[{'type':'integer','value':'7'},{'type':'null'}]]}}}]})
        self.assertEqual(rows,[{'id':7,'note':None}])
        with patch.dict(os.environ,{'TURSO_DATABASE_URL':'libsql://example.turso.io','TURSO_AUTH_TOKEN':'test-only-token'}):
            self.assertEqual(server.endpoint()[0],'https://example.turso.io/v2/pipeline')

if __name__ == '__main__':
    unittest.main()
