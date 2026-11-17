import importlib.util
import json
import os
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
spec=importlib.util.spec_from_file_location('server_v3',Path(__file__).with_name('server.py'))
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

class PaginationTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'APP_PASSWORD':'test-password-12345','SESSION_SECRET':'test-secret-never-use-in-production-12345','TURSO_DATABASE_URL':'libsql://test.invalid'})
        self.env.start();server._schema_cache.clear();server._metadata_cache.clear();server.failures.clear()
        self.db=sqlite3.connect(':memory:',check_same_thread=False)
        self.db.executescript('''
        CREATE TABLE articles (Link TEXT PRIMARY KEY,Title TEXT,Source TEXT,Summary TEXT,Image TEXT,SortDate TEXT,is_bookmarked INTEGER,comment TEXT);
        CREATE TABLE academic_pubs (id INTEGER PRIMARY KEY,type TEXT,title TEXT,author TEXT,publisher_journal TEXT,identifier TEXT,publish_date TEXT,abstract TEXT,link TEXT,image TEXT,book_status INTEGER,category TEXT,issue_volume TEXT);
        CREATE TABLE media_vault (id INTEGER PRIMARY KEY,title TEXT,creator TEXT,media_type TEXT,is_bookmarked INTEGER,sort_date TEXT);
        CREATE TABLE omni_vault (id INTEGER PRIMARY KEY,title TEXT,category TEXT,image_url TEXT,comment TEXT,added_date TEXT);
        CREATE TABLE custom_resources (id INTEGER PRIMARY KEY,module TEXT,title TEXT,added_date TEXT);
        CREATE TABLE bibliography_notes (id INTEGER PRIMARY KEY,title TEXT,notes TEXT,importance TEXT,added_date TEXT);
        ''')
        self.db.executemany('INSERT INTO articles VALUES (?,?,?,?,?,?,?,?)',[(f'https://example/{i}',f'文章 {i:04}', 'Review' if i%2 else 'WIRED.jp','x'*1400+('NeedleBeyondExcerpt' if i==1 else ''),'','2020-01-01T00:00:00',i%2,'筆記') for i in range(780)])
        self.db.execute("INSERT INTO articles VALUES ('new1','RecentReview','Review','','',datetime('now'),0,'')")
        self.db.execute("INSERT INTO articles VALUES ('new2','RecentNews','WIRED.jp','','',datetime('now'),0,'')")
        self.db.executemany('INSERT INTO academic_pubs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',[(i,'Book' if i%2 else 'Journal',f'Book {i}', 'Author','Press',str(i),'2020-01-01','','','',i%5,'研究','Vol 1') for i in range(620)])
        self.db.execute("INSERT INTO academic_pubs VALUES (1000,'Web Link','SavedURL','','','','2021-01-01','','','',1,'','')")
        self.db.executemany('INSERT INTO media_vault VALUES (?,?,?,?,?,?)',[(1,'MovieWait','Director','電影',1,'2020-01-01'),(2,'MusicArchive','Artist','專輯',0,'2020-01-01')])
        self.db.executemany('INSERT INTO omni_vault VALUES (?,?,?,?,?,?)',[(1,'Art1','Art','','','2020-01-01'),(2,'Art2','Art','','','2020-01-01'),(3,'Coffee','Coffee','','','2020-01-01')])
        self.db.executemany('INSERT INTO custom_resources VALUES (?,?,?,?)',[(1,'monoreader','Mono site','2020-01-01'),(2,'biblioapp','Research site','2020-01-01'),(3,'biblioapp_lecture','Lecture','2020-01-01'),(4,'media_vault','Media site','2020-01-01')])
        self.db.execute("INSERT INTO bibliography_notes VALUES (1,'Reference','Full note','S','2020-01-01')")
        self.sql=[]
        async def query(sql,args=None):
            self.sql.append((sql,args));self.assertTrue(sql.startswith('SELECT '))
            c=self.db.execute(sql,args or [])
            cols=[x[0] for x in c.description]
            return cols,[dict(zip(cols,row)) for row in c.fetchall()]
        self.patch=patch.object(server,'query',query);self.patch.start()
        self.client=TestClient(server.app,base_url='https://testserver')
        self.client.post('/login',data={'password':'test-password-12345'})
    def tearDown(self):
        self.client.close();self.patch.stop();self.db.close();self.env.stop()
    def browse(self,**params):
        r=self.client.get('/api/browse',params=params);self.assertEqual(r.status_code,200,r.text);return r.json()
    def test_archive_pages_and_search_beyond_500(self):
        a=self.browse(tab='分類存檔',sort='title',asc=True)
        b=self.browse(tab='分類存檔',sort='title',asc=True,page=20)
        self.assertEqual(a['total'],782);self.assertEqual(len(a['items']),30)
        self.assertFalse({x['id'] for x in a['items']}&{x['id'] for x in b['items']})
        result=self.browse(tab='分類存檔',q='文章 0779')
        self.assertEqual(result['total'],1)
        self.assertEqual(self.browse(tab='搜尋中心',q='NeedleBeyondExcerpt')['total'],1)
        self.assertEqual(self.browse(tab='分類存檔',q="' OR 1=1 --")['total'],0)
        self.assertEqual(self.browse(tab='分類存檔',q='%')['total'],0)
    def test_shelf_page_size_and_complete_last_page(self):
        first=self.browse(module='bib',tab='文獻探索',sub='出版專書')
        second=self.browse(module='bib',tab='文獻探索',sub='出版專書',page=2)
        self.assertEqual(first['page_size'],18)
        self.assertEqual(len(first['items']),18)
        self.assertFalse({x['id'] for x in first['items']}&{x['id'] for x in second['items']})
        last=self.browse(module='bib',tab='文獻探索',sub='出版專書',page=999)
        self.assertEqual(last['page'],18)
        self.assertEqual(len(last['items']),4)
        for module,tab,sub in [('bib','個人書庫','待讀書架'),('media','待播／待看','電影與影集'),('media','典藏／已完成','音樂與專輯')]:
            self.assertEqual(self.browse(module=module,tab=tab,sub=sub)['page_size'],18)
        for module,tab,sub in [('mono','分類存檔',''),('bib','參考書目',''),('bib','文獻探索','期刊論文'),('media','待播／待看','網路資源分享卡')]:
            self.assertEqual(self.browse(module=module,tab=tab,sub=sub)['page_size'],30)

    def test_recent_and_saved(self):
        self.assertEqual(self.browse()['total'],2)
        self.assertEqual(self.browse(tab='最新評論')['total'],1)
        self.assertEqual(self.browse(tab='文化快訊')['items'][0]['title'],'RecentNews')
        self.assertEqual(self.browse(tab='我的收藏庫')['total'],390)
    def test_books_and_full_facets(self):
        for status,shelf in enumerate(['待讀書架','已讀書籍','實體書庫','電子書架'],1):
            r=self.browse(module='bib',tab='個人書庫',sub=shelf)
            self.assertEqual(r['total'],124)
            self.assertTrue(all(x['shelf']==shelf for x in r['items']))
        self.assertEqual(self.browse(module='bib',tab='網址備存')['total'],1)
        self.assertEqual(self.browse(module='bib',tab='文獻探索',sub='期刊論文')['total'],310)
        self.assertEqual(self.browse(module='bib',tab='參考書目')['items'][0]['notes'],'Full note')
        self.assertEqual(self.browse(module='bib',tab='可用資源',sub='講座記錄')['total'],1)
        r=self.browse(tab='分類存檔',source='Review');self.assertIn('WIRED.jp',r['sources'])
        self.assertTrue(all(x['source']=='Review' for x in r['items']))
    def test_module_search_media_and_folders(self):
        self.assertEqual(self.browse(module='bib',tab='搜尋中心',q='site')['total'],1)
        self.assertEqual(self.browse(module='media',tab='典藏／已完成',sub='音樂與專輯')['items'][0]['title'],'MusicArchive')
        self.assertEqual(self.browse(module='media',tab='待播／待看',sub='電影與影集')['total'],1)
        folders=self.client.get('/api/folders').json()['folders']
        self.assertEqual({x['name']:x['total'] for x in folders},{'Art':2,'Coffee':1})
        self.assertEqual(self.browse(module='omni',tab='分類資料夾',folder='Art')['total'],2)
    def test_full_detail_payload_and_stats(self):
        item=self.browse(tab='分類存檔',q='NeedleBeyondExcerpt')['items'][0]
        self.assertEqual(len(item['summary']),1200)
        detail=self.client.get('/api/item',params={'module':'mono','id':item['id']}).json()
        self.assertIn('NeedleBeyondExcerpt',detail['summary'])
        self.assertEqual(self.client.get('/api/stats').json()['articles'],782)
        self.assertEqual(self.browse(tab='分類存檔',page=999)['page'],27)
    def test_auth_and_login_regression(self):
        self.assertEqual(self.client.get('/login').headers['referrer-policy'],'strict-origin-when-cross-origin')
        self.assertIn('window.MONOREADER_BOOT=',self.client.get('/').text)
        self.assertEqual(self.client.post('/login',headers={'origin':'null'},data={'password':'test-password-12345'}).status_code,403)
        with patch.dict(os.environ,{'APP_ALLOWED_ORIGINS':'https://reader.example'}):
            self.assertEqual(self.client.post('/login',headers={'origin':'https://reader.example'},data={'password':'test-password-12345'},follow_redirects=False).status_code,303)
        self.client.post('/logout')
        for path in ['/api/browse','/api/folders','/api/stats','/api/item?module=mono&id=x','/api/session']:
            self.assertEqual(self.client.get(path).status_code,401)
    def test_missing_table_and_validation(self):
        self.db.execute('DROP TABLE articles');server._schema_cache.clear()
        self.assertEqual(self.browse(tab='分類存檔')['total'],0)
        self.assertIsNone(self.client.get('/api/stats').json()['articles'])
        for params in ({'module':'bad'},{'sort':'title;DROP TABLE articles'},{'page':0}):
            self.assertEqual(self.client.get('/api/browse',params=params).status_code,400)

if __name__=='__main__':unittest.main()
