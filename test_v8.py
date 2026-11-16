import asyncio
import sqlite3
from unittest.mock import patch,AsyncMock
from test_writes import WriteTests,server
import metadata

class V8Tests(WriteTests):
    def setUp(self):
        super().setUp()
        self.writer.stop()
        async def write(sql,args):
            self.assertTrue(sql.startswith(('UPDATE "','INSERT INTO "','DELETE FROM "')))
            try:c=self.db.execute(sql,args)
            except sqlite3.IntegrityError:raise server.HTTPException(409,"資料限制")
            names=[v[0] for v in c.description]
            return names,[dict(zip(names,r)) for r in c.fetchall()]
        self.writer=patch.object(server,'write_query',write);self.writer.start()
    def test_delete_confirmation_conflict_and_success(self):
        d=self.detail('bib','academic_pubs:1000')
        body={'module':'bib','id':d['id'],'revision':d['_revision'],'confirmed':False}
        self.assertEqual(self.post('/api/delete',body).status_code,400)
        body['confirmed']=True
        self.assertEqual(self.post('/api/delete',body,'https://evil.invalid').status_code,403)
        with patch.dict('os.environ',{'ENABLE_WRITES':'false'}):
            self.assertEqual(self.post('/api/delete',body).status_code,403)
        self.db.execute("UPDATE academic_pubs SET title='changed' WHERE id=1000")
        self.assertEqual(self.post('/api/delete',body).status_code,409)
        body['revision']=self.detail('bib',d['id'])['_revision']
        self.assertEqual(self.post('/api/delete',body).status_code,200)
        self.assertIsNone(self.db.execute('SELECT id FROM academic_pubs WHERE id=1000').fetchone())
        self.assertEqual(self.post('/api/delete',body).status_code,404)
    def test_delete_all_tables_and_scope(self):
        cases=[('mono','articles:https://example/1'),('bib','bibliography_notes:1'),('media','media_vault:1'),('omni','omni_vault:1'),('mono','custom_resources:1')]
        for module,id in cases:
            d=self.detail(module,id)
            body={'module':module,'id':id,'revision':d['_revision'],'confirmed':True}
            self.assertEqual(self.post('/api/delete',body).status_code,200)
        d=self.detail('bib','custom_resources:2')
        self.assertEqual(self.post('/api/delete',{'module':'mono','id':d['id'],'revision':d['_revision'],'confirmed':True}).status_code,400)
    def test_dates_from_sample_columns(self):
        self.db.execute('ALTER TABLE academic_pubs ADD COLUMN created_at TEXT')
        self.db.execute("UPDATE academic_pubs SET created_at='2026-11-16' WHERE id=1")
        self.db.execute('ALTER TABLE articles ADD COLUMN Published TEXT')
        self.db.execute("UPDATE articles SET Published='2025-02-01' WHERE Link='https://example/1'")
        server._schema_cache.clear()
        self.assertEqual(self.detail('bib','academic_pubs:1')['added'],'2026-11-16')
        self.assertEqual(self.detail('mono','articles:https://example/1')['published'],'2025-02-01')
    def test_douban_isbn_validation(self):
        html='<span property="v:itemreviewed">中文書</span><div id="info">作者: 作者甲 出版社: 出版社乙 ISBN: 9787101003048</div><div id="mainpic"><img src="https://img.example/cover.jpg"></div><div class="intro">摘要</div>'
        with patch.object(metadata,'douban_html',new=AsyncMock(return_value=(html,'https://book.douban.com/subject/1/'))):
            b=asyncio.run(metadata.lookup_douban('9787101003048'))
            self.assertEqual(b['provider'],'豆瓣');self.assertEqual(b['fields']['author'],'作者甲')
            with self.assertRaises(server.HTTPException):asyncio.run(metadata.lookup_douban('9787101003049'))
    def test_japanese_missing_cover(self):
        with patch.object(metadata,'provider_json',new=AsyncMock(return_value=[{'summary':{'title':'日本語書籍'}}])),patch.object(metadata,'japanese_cover',new=AsyncMock(return_value='https://www.hanmoto.com/bd/img/9784003101018.jpg')):
            b=asyncio.run(metadata.lookup_isbn('9784003101018'))
            self.assertEqual(b['provider'],'openBD')
            self.assertIn('hanmoto',b['fields']['image'])
