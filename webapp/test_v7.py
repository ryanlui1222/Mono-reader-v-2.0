from test_server import PaginationTests
class V7Tests(PaginationTests):
    def test_large_cover_and_auth(self):
        value='data:image/png;base64,'+'AAAA'*10000
        self.db.execute("UPDATE academic_pubs SET image=? WHERE id=1",(value,))
        b=self.browse(module='bib',tab='個人書庫',sub='待讀書架',q='Book 1')
        item=next(x for x in b['items'] if x['id']=='academic_pubs:1')
        self.assertTrue(item['image'].startswith('/api/image?'))
        r=self.client.get(item['image'])
        self.assertEqual(r.status_code,200)
        self.assertEqual(len(r.content),30000)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(item['image']).status_code,401)
    def test_health_and_no_mutations(self):
        self.assertFalse(self.client.get('/api/crawler-health').json()['available'])
        self.db.execute('CREATE TABLE crawler_health(source_name TEXT,status TEXT,last_check TEXT,error_msg TEXT)')
        self.db.executemany('INSERT INTO crawler_health VALUES(?,?,?,?)',[
          ('bad','ERROR','2020-01-01','failure'),('empty','EMPTY','2020-01-01',''),
          ('ok','OK','2020-01-01',''),('unknown','ERROR','bad date','')])
        before=self.db.total_changes
        b=self.client.get('/api/crawler-health').json()
        self.assertEqual(b['alerts'],2)
        self.assertEqual(self.db.total_changes,before)
        self.assertIsNone(next(x for x in b['items'] if x['source_name']=='unknown')['hours'])
    def test_categories_and_shelf_filter(self):
        self.db.execute("UPDATE academic_pubs SET category='自訂分類' WHERE id=1")
        self.assertIn('自訂分類',self.client.get('/api/categories?module=bib').json()['categories'])
        b=self.browse(module='bib',tab='個人書庫',sub='待讀書架',source='自訂分類')
        self.assertEqual(b['total'],1)
