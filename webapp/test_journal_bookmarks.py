from unittest.mock import patch
from test_writes import WriteTests, server

class JournalBookmarks(WriteTests):
    def setUp(self):
        super().setUp()
        self.db.execute('ALTER TABLE academic_pubs ADD COLUMN is_bookmarked INTEGER DEFAULT 0')
        server._schema_cache.clear()
    def test_journal_round_trip(self):
        before=self.db.execute('SELECT * FROM academic_pubs WHERE id=2').fetchone()
        for _ in range(2):
            r=self.post('/api/bookmark',{'module':'bib','id':'academic_pubs:2','saved':True})
            self.assertEqual(r.status_code,200,r.text)
        after=self.db.execute('SELECT * FROM academic_pubs WHERE id=2').fetchone()
        self.assertEqual(before[:-1],after[:-1]);self.assertEqual(after[-1],1)
        result=self.browse(module='bib',tab='待讀期刊')
        self.assertEqual(result['total'],1);self.assertEqual(result['items'][0]['id'],'academic_pubs:2')
        self.assertIn('Press',result['sources']);self.assertIn('Vol 1',result['issues'])
        self.assertEqual(self.browse(module='bib',tab='待讀期刊',source='Press',issue='Vol 1',q='Book 2')['total'],1)
        self.assertEqual(self.browse(module='bib',tab='待讀期刊',q='missing')['total'],0)
        r=self.post('/api/bookmark',{'module':'bib','id':'academic_pubs:2','saved':False})
        self.assertEqual(r.status_code,200)
        server._metadata_cache.clear()
        self.assertEqual(self.browse(module='bib',tab='待讀期刊')['total'],0)
        self.assertEqual(self.db.execute('SELECT * FROM academic_pubs WHERE id=2').fetchone(),before)
    def test_no_books_links_or_unauthorized_writes(self):
        for id in ('academic_pubs:1','academic_pubs:1000','bibliography_notes:1'):
            self.assertEqual(self.post('/api/bookmark',{'module':'bib','id':id,'saved':True}).status_code,400)
        body={'module':'bib','id':'academic_pubs:2','saved':True}
        self.assertEqual(self.post('/api/bookmark',body,'https://evil.example').status_code,403)
        with patch.dict('os.environ',{'ENABLE_WRITES':'false'}):
            self.assertEqual(self.post('/api/bookmark',body).status_code,403)
        self.assertEqual(self.post('/api/bookmark',{**body,'saved':'true'}).status_code,400)
    def test_shelves_only_contain_books(self):
        result=self.browse(module='bib',tab='個人書庫',sub='待讀書架')
        self.assertTrue(result['items']);self.assertTrue(all(x['type']=='book' for x in result['items']))
    def test_legacy_mono_bookmark(self):
        self.assertEqual(self.post('/api/bookmark',{'id':'articles:new1','saved':True}).status_code,200)
        self.assertEqual(self.db.execute("SELECT is_bookmarked FROM articles WHERE Link='new1'").fetchone()[0],1)
