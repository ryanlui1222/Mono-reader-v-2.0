from test_server import PaginationTests, server

class PerformanceTests(PaginationTests):
    def test_next_page_only_queries_rows_and_force_rechecks_metadata(self):
        params={'module':'mono','tab':'分類存檔','page':1}
        self.client.get('/api/browse',params=params).raise_for_status()
        self.sql.clear()
        params['page']=2
        self.client.get('/api/browse',params=params).raise_for_status()
        self.assertEqual(len(self.sql),1)
        self.assertIn('LIMIT ? OFFSET ?',self.sql[0][0])
        self.sql.clear()
        params['refresh']='1'
        self.client.get('/api/browse',params=params).raise_for_status()
        self.assertGreater(len(self.sql),1)
    def test_metadata_cache_does_not_bypass_login(self):
        self.client.get('/api/browse').raise_for_status()
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/browse').status_code,401)
