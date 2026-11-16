import unittest
from test_server import PaginationTests,server
class FolderTests(unittest.TestCase):
    tearDown=PaginationTests.tearDown
    browse=PaginationTests.browse
    def setUp(self):
        PaginationTests.setUp(self)
        self.db.execute('DELETE FROM academic_pubs')
        for i,(typ,source,issue,date) in enumerate([
            ('Book','Duke','', '2026-11'),('Book','Duke University Press','','2026-06-01'),
            ('Book','東京大学出版会','','2026'),('Book','Other Press','','2026-11-02'),
            ('Journal','Test Journal','Vol. 2, Issue 10','2026-11'),
            ('Journal','Test Journal','Vol. 2, Issue 10','2026-11'),
            ('Journal','Test Journal','Vol. 2, Issue 2','2026-06'),
            ('Journal','Test Journal','','2026-11-10'),
            ('Journal','Test Journal','','2026-11-15'),
            ('Journal','Test Journal','',''),
            ('Journal','Other Journal','Vol. 2, Issue 10','2026-11')]):
            self.db.execute('INSERT INTO academic_pubs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(i,typ,'Title '+str(i),'Author',source,str(i),date,'','','',0,'研究',issue))
    def test_home_groups_and_aliases(self):
        body=self.client.get('/api/explore').json()
        self.assertEqual(len(body['publishers']),5)
        self.assertEqual(next(x for x in body['publishers'] if x['name']=='Duke University Press')['total'],2)
        self.assertEqual(body['other_publishers'][0]['name'],'Other Press')
        self.assertEqual(len(body['journal_folders']),2)
    def test_issue_folders_and_exact_contents(self):
        b=self.client.get('/api/explore',params={'source':'Test Journal'}).json()
        groups={x['key']:x for x in b['issue_folders']}
        self.assertEqual(groups['issue:Vol. 2, Issue 10']['total'],2)
        self.assertEqual(groups['month:2026-11']['total'],2)
        self.assertIn('unknown:',groups)
        for key,count in [('issue:Vol. 2, Issue 10',2),('month:2026-11',2),('unknown:',1)]:
            data=self.browse(module='bib',tab='文獻探索',sub='期刊論文',bsource='Test Journal',bissue=key)
            self.assertEqual(data['total'],count)
            self.assertTrue(all(x['source']=='Test Journal' for x in data['items']))
    def test_publisher_alias_and_partial_dates(self):
        b=self.browse(module='bib',tab='文獻探索',sub='出版專書',bsource='Duke University Press',sort='published')
        self.assertEqual(b['total'],2)
        self.assertEqual([x['published'] for x in b['items']],['2026-11','2026-06-01'])
        self.assertEqual(self.browse(module='bib',tab='文獻探索',sub='出版專書',bsource='Duke University Press',q='Title 1')['total'],1)
    def test_empty_and_login(self):
        self.assertEqual(self.client.get('/api/explore',params={'source':'Missing'}).json()['issue_folders'],[])
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/explore').status_code,401)
