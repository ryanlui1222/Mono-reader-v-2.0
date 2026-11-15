import asyncio
import os
from unittest.mock import AsyncMock, patch
import httpx
import metadata
from test_writes import WriteTests


class FeatureTests(WriteTests):
    def test_journal_folders_latest_and_past(self):
        sources=['e-flux Journal (Issue 0)','e-flux Journal (Issue 2)','e-flux Journal (Issue 10)','e-flux Journal (Issue 110)',
                 'The Funambulist (Issue 67) (Older theme)','The Funambulist (Issue 68) (Latest theme)','The Point (35)','421 News (EN)','421 News (ZH)']
        for i,source in enumerate(sources):
            self.db.execute('INSERT INTO articles VALUES (?,?,?,?,?,?,?,?)',(f'journal:{i}',f'Issue title {i}',source,'','','2020-01-01',0,''))
        args={'module':'mono','tab':'分類存檔'}
        body=self.client.get('/api/browse',params=args).json()
        self.assertIn('e-flux Journal',body['sources'])
        self.assertNotIn(sources[0],body['sources'])
        group=next(j for j in body['journals'] if j['name']=='e-flux Journal')
        self.assertEqual(group['latest'],sources[3]);self.assertEqual(group['issues'],4)
        args.update(source='e-flux Journal',issue='最新')
        body=self.client.get('/api/browse',params=args).json()
        self.assertEqual(body['total'],1)
        self.assertEqual(body['selected_issue'],sources[3])
        self.assertEqual(body['issues'],list(reversed(sources[:4])))
        self.assertEqual(body['items'][0]['source'],sources[3])
        args['issue']=sources[1]
        self.assertEqual(self.client.get('/api/browse',params=args).json()['items'][0]['source'],sources[1])
        args['issue']='全部'
        self.assertEqual(self.client.get('/api/browse',params=args).json()['total'],4)
        args.update(issue='最新',q='title 1')
        body=self.client.get('/api/browse',params=args).json()
        self.assertEqual(body['total'],0);self.assertEqual(body['selected_issue'],sources[3])
        args.update(issue=sources[4],q='')
        self.assertEqual(self.client.get('/api/browse',params=args).status_code,400)

    def test_bookmark_atomic_idempotent_and_favorites(self):
        id='articles:https://example/2'
        for _ in range(2):
            r=self.post('/api/bookmark',{'id':id,'saved':True});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.db.execute("SELECT is_bookmarked,comment FROM articles WHERE Link='https://example/2'").fetchone(),(1,'筆記'))
        body=self.client.get('/api/browse',params={'module':'mono','tab':'我的收藏庫','q':'文章 0002'}).json()
        self.assertEqual(body['total'],1)
        self.assertEqual(self.post('/api/bookmark',{'id':id,'saved':False}).status_code,200)
        body=self.client.get('/api/browse',params={'module':'mono','tab':'我的收藏庫','q':'文章 0002'}).json()
        self.assertEqual(body['total'],0)
        self.assertIsNotNone(self.db.execute("SELECT Link FROM articles WHERE Link='https://example/2'").fetchone())
        self.assertEqual(self.post('/api/bookmark',{'id':id,'saved':'true'}).status_code,400)
        self.assertEqual(self.post('/api/bookmark',{'id':id,'saved':True},'null').status_code,403)
        with patch.dict(os.environ,{'ENABLE_WRITES':'false'}):
            self.assertEqual(self.post('/api/bookmark',{'id':id,'saved':True}).status_code,403)

    def test_isbn_draft_does_not_write(self):
        before=self.db.total_changes
        google={'items':[{'volumeInfo':{'title':'Fixture Book','authors':['Fixture Author'],'publisher':'Chicago','industryIdentifiers':[{'type':'ISBN_13','identifier':'9780674040212'}],'description':'<p>Summary &amp; text</p>','imageLinks':{'thumbnail':'http://books.google.com/cover'},'infoLink':'https://books.google.com/book'}}]}
        with patch.object(metadata,'provider_json',new=AsyncMock(return_value=google)) as upstream:
            r=self.post('/api/lookup',{'kind':'isbn','value':'978-0-674-04021-2'})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['fields']['title'],'Fixture Book')
            self.assertEqual(r.json()['fields']['summary'],'Summary & text')
            self.assertEqual(upstream.await_count,1)
        self.assertEqual(self.db.total_changes,before)

    def test_wrong_isbn_match_falls_back_and_validates(self):
        payloads=[{'items':[{'volumeInfo':{'title':'Wrong edition','industryIdentifiers':[{'identifier':'9780674040212'}]}}]},
                  {'ISBN:9780140328721':{'title':'Matilda','authors':[{'name':'Roald Dahl'}]}}]
        with patch.object(metadata,'provider_json',new=AsyncMock(side_effect=payloads)):
            r=self.post('/api/lookup',{'kind':'isbn','value':'9780140328721'})
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['provider'],'Open Library')
        with patch.object(metadata,'provider_json',new=AsyncMock()) as upstream:
            self.assertEqual(self.post('/api/lookup',{'kind':'isbn','value':'9780140328722'}).status_code,400)
            self.assertEqual(upstream.await_count,0)
        self.assertEqual(metadata.isbn13('0140328726'),'9780140328721')

    def test_imdb_movie_series_and_missing_key(self):
        with patch.dict(os.environ,{'TMDB_API_KEY':''}):
            self.assertEqual(self.post('/api/lookup',{'kind':'imdb','value':'tt0137523'}).status_code,503)
        for kind,item,detail in [('movie',{'id':550,'title':'Fight Club','poster_path':'/poster.jpg'},{'credits':{'crew':[{'job':'Director','name':'David Fincher'}]}}),
                                 ('tv',{'id':1399,'name':'TV Series'},{'created_by':[{'name':'Creator'}]})]:
            with patch.dict(os.environ,{'TMDB_API_KEY':'fake-secret'}),patch.object(metadata,'provider_json',new=AsyncMock(side_effect=[{kind+'_results':[item]},detail])):
                r=self.post('/api/lookup',{'kind':'imdb','value':'https://www.imdb.com/title/tt0137523/?ref_=test'})
                self.assertEqual(r.status_code,200,r.text)
                self.assertTrue(r.json()['fields']['author']);self.assertNotIn('fake-secret',r.text)
        with patch.object(metadata,'provider_json',new=AsyncMock()) as upstream:
            self.assertEqual(self.post('/api/lookup',{'kind':'imdb','value':'https://imdb.com.evil.test/title/tt0137523/'}).status_code,400)
            self.assertEqual(upstream.await_count,0)

    def test_doi_and_apple(self):
        with patch.object(metadata,'provider_json',new=AsyncMock(return_value={'message':{'title':['Paper'],'author':[{'given':'A','family':'B'}],'published':{'date-parts':[[2013,11]]},'container-title':['Journal'],'volume':'9','issue':'3'}})):
            r=self.post('/api/lookup',{'kind':'doi','value':'https://doi.org/10.1215/17432197-2347000'})
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['fields']['published'],'2013-11')
        with patch.object(metadata,'provider_json',new=AsyncMock(return_value={'results':[{'collectionId':123,'wrapperType':'collection','collectionName':'Album','artistName':'Artist'}]})):
            r=self.post('/api/lookup',{'kind':'apple','value':'https://music.apple.com/hk/album/album-name/123'})
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['category'],'音樂與專輯')

    def test_provider_failure_does_not_expose_keys(self):
        original=httpx.AsyncClient
        def response(request):return httpx.Response(403,json={'error':'secret upstream value'})
        with patch.object(metadata.httpx,'AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(response),**kw)):
            with self.assertRaises(metadata.HTTPException) as exc:
                asyncio.run(metadata.provider_json('https://api.themoviedb.org/3/find/tt0137523',{'api_key':'never-echo-this'}))
            self.assertNotIn('never-echo-this',exc.exception.detail)
