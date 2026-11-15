import json
import os
import sqlite3
from unittest.mock import patch
from test_server import PaginationTests,server

class WriteTests(PaginationTests):
    def setUp(self):
        super().setUp()
        self.write_env=patch.dict(os.environ,{'ENABLE_WRITES':'true'});self.write_env.start()
        async def write_query(sql,args):
            self.assertTrue(sql.startswith(('UPDATE "','INSERT INTO "')))
            try:
                c=self.db.execute(sql,args);cols=[d[0] for d in c.description]
                return cols,[dict(zip(cols,r)) for r in c.fetchall()]
            except sqlite3.IntegrityError:
                raise server.HTTPException(409,'重複或資料限制')
        self.writer=patch.object(server,'write_query',write_query);self.writer.start()
    def tearDown(self):
        self.writer.stop();self.write_env.stop();super().tearDown()
    def post(self,path,data,origin='https://testserver'):
        return self.client.post(path,json=data,headers={'origin':origin})
    def detail(self,module,id):
        r=self.client.get('/api/item',params={'module':module,'id':id});self.assertEqual(r.status_code,200,r.text);return r.json()
    def change(self,module,id,changes,revision=None):
        d=self.detail(module,id)
        return self.post('/api/update',{'module':module,'id':id,'revision':revision or d['_revision'],'changes':changes})
    def test_write_notes_and_status(self):
        d=self.detail('mono','articles:https://example/1');self.assertIn('notes',d['_editable'])
        r=self.change('mono',d['id'],{'notes':'長筆記\n第二段 😀', 'saved':False});self.assertEqual(r.status_code,200,r.text)
        raw=self.db.execute("SELECT comment,is_bookmarked FROM articles WHERE Link='https://example/1'").fetchone()
        self.assertEqual(raw,('長筆記\n第二段 😀',0))
        self.assertEqual(self.change('bib','academic_pubs:1',{'shelf':'電子書架'}).status_code,200)
        self.assertEqual(self.db.execute('SELECT book_status FROM academic_pubs WHERE id=1').fetchone()[0],4)
        self.assertEqual(self.change('media','media_vault:1',{'stage':'典藏'}).status_code,200)
        self.assertEqual(self.change('omni','omni_vault:1',{'category':'New Folder'}).status_code,200)
    def test_conflict_preserves_newer_notes(self):
        d=self.detail('bib','bibliography_notes:1')
        self.db.execute("UPDATE bibliography_notes SET notes='Written elsewhere' WHERE id=1")
        r=self.change('bib',d['id'],{'notes':'Stale draft'},d['_revision'])
        self.assertEqual(r.status_code,409)
        self.assertEqual(self.db.execute('SELECT notes FROM bibliography_notes WHERE id=1').fetchone()[0],'Written elsewhere')
    def test_gate_origin_validation_no_delete(self):
        d=self.detail('omni','omni_vault:1');body={'module':'omni','id':d['id'],'revision':d['_revision'],'changes':{'title':'Modified'}}
        with patch.dict(os.environ,{'ENABLE_WRITES':'false'}):self.assertEqual(self.post('/api/update',body).status_code,403)
        for origin in ('null','https://evil.example'):self.assertEqual(self.post('/api/update',body,origin).status_code,403)
        self.assertEqual(self.client.post('/api/update',json=body).status_code,403)
        self.assertEqual(self.change('omni',d['id'],{'url':'javascript:alert(1)'}).status_code,400)
        self.assertEqual(self.change('omni',d['id'],{'title':''}).status_code,400)
        self.assertEqual(self.change('omni',d['id'],{'sql':'DROP TABLE omni_vault'}).status_code,400)
        self.assertEqual(self.client.delete('/api/item',params={'module':'omni','id':d['id']}).status_code,405)
    def test_create_types_and_duplicate(self):
        cases=[('mono','article',{'title':'ManualArticle','url':'https://new.example/article','notes':'Comment'}),
               ('bib','book',{'title':'ManualBook','author':'A','shelf':'實體書庫'}),
               ('bib','reference',{'title':'ManualRef','notes':'Long reference note','rating':'A'}),
               ('bib','bibLink',{'title':'ManualLink','url':'https://book.example'}),
               ('omni','omni',{'title':'New item','category':'NewFolder','notes':'New note'}),
               ('media','media',{'title':'ManualFilm','stage':'待播'}),
               ('bib','bibResource',{'title':'Research link'})]
        for module,kind,fields in cases:
            r=self.post('/api/create',{'module':module,'type':kind,'fields':fields})
            self.assertEqual(r.status_code,200,(kind,r.text))
            self.assertEqual(self.detail(module,r.json()['id'])['title'],fields['title'])
        r=self.post('/api/create',{'module':'mono','type':'article','fields':cases[0][2]})
        self.assertEqual(r.status_code,409)
    def test_missing_notes_column_not_silently_saved(self):
        self.assertNotIn('notes',self.detail('bib','academic_pubs:1')['_editable'])
        self.assertEqual(self.change('bib','academic_pubs:1',{'notes':'Not supported'}).status_code,400)
    def test_write_transport_binds_null_and_text(self):
        # Exercise actual HTTP serialization, not only SQLite query generation.
        import asyncio,httpx
        captured=[]
        async def handler(req):
            captured.append(json.loads(req.content))
            return httpx.Response(200,json={'results':[{'type':'ok','response':{'result':{'cols':[{'name':'id'}],'rows':[[{'type':'integer','value':'1'}]]}}}]})
        original=httpx.AsyncClient
        with patch.dict(os.environ,{'TURSO_AUTH_TOKEN':'test-only'}),patch.object(server.httpx,'AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            asyncio.run(server.execute_sql('UPDATE "test" SET note=? WHERE id IS ? RETURNING id',["quote ' ; --",None]))
        args=captured[0]['requests'][0]['stmt']['args']
        self.assertEqual(args,[{'type':'text','value':"quote ' ; --"},{'type':'null'}])
