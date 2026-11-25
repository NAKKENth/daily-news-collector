import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from collector import iso_utc,local_day,canonical_url,parse_rss,parse_gh_releases,parse_gh_pulls,connect_db,insert_items,query_group,write_report,collect_one,build

MOCK_RSS=b'''<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>Sample</title><item><title>New product</title><link>https://example.org/news/1?utm_source=abc</link><pubDate>Tue, 24 Nov 2026 20:05:00 GMT</pubDate><description>Announced.</description></item></channel></rss>'''
SOURCE={'id':'test-rss','kind':'rss','label':'Test','group':'audio','topic':'wired','role':'specialist','domain':'example.org','feed_url':'https://example.org/feed/'}
T='2026-11-25T06:00:00+00:00'

class TestCollector(unittest.TestCase):
 def test_jst_date(self):
  t=iso_utc('Tue, 24 Nov 2026 20:05:00 GMT')
  self.assertEqual(local_day(t),'2026-11-25')
  self.assertIsNone(iso_utc('2026-11-24T12:00:00'))
 def test_strip_tracking(self):
  self.assertEqual(canonical_url('https://EXAMPLE.org/a/?utm_source=a&x=2#abc'),'https://example.org/a?x=2')
 def test_rss_publication_is_only_article_date(self):
  a=parse_rss(MOCK_RSS,SOURCE,T)
  self.assertEqual(len(a),1)
  self.assertEqual(a[0]['timestamp_basis'],'source_feed_published')
  self.assertEqual(a[0]['date_jst'],'2026-11-25')
 def test_atom(self):
  atom=b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Test release</title><link href="https://example.org/a" rel="alternate"/><updated>2026-11-24T14:00:00Z</updated></entry></feed>'''
  self.assertEqual(parse_rss(atom,SOURCE,T)[0]['date_jst'],'2026-11-24')
 def test_google_news_label(self):
  a=parse_rss(MOCK_RSS,dict(SOURCE,kind='news'),T)
  self.assertEqual(a[0]['link_role'],'discovery_link')
  self.assertEqual(a[0]['timestamp_basis'],'google_news_index')
 def test_github_release_vs_pr(self):
  s=dict(SOURCE,kind='github_releases',repository='x/y')
  a=parse_gh_releases([{'html_url':'https://github.com/x/y/releases/tag/v1','name':'v1','published_at':'2026-11-24T16:00:00Z','body':'fixed bugs'}],s,T)
  self.assertEqual(a[0]['date_jst'],'2026-11-25')
  self.assertEqual(a[0]['timestamp_basis'],'github_release_published')
  b=parse_gh_pulls([{'html_url':'https://github.com/x/y/pull/11','number':11,'title':'Fix','merged_at':'2026-11-24T16:00:00Z'}],s,T)
  self.assertEqual(b[0]['timestamp_basis'],'github_pr_merged')
 def test_rdf_feed_1_0(self):
  xml=b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"><item><title>Japanese PC news</title><link>https://example.org/pc</link><dc:date>2026-11-24T15:10:00+00:00</dc:date></item></rdf:RDF>'''
  a=parse_rss(xml,SOURCE,T)
  self.assertEqual(len(a),1)
  self.assertEqual(a[0]['date_jst'],'2026-11-25')
 def test_broken_feed_google_discovery_fallback(self):
  with patch('collector.request_data',side_effect=[RuntimeError('HTTP 403'),MOCK_RSS]):
   items,health=collect_one(SOURCE,T,'')
  self.assertEqual(health['status'],'partial')
  self.assertEqual(items[0]['timestamp_basis'],'google_news_index')
  self.assertIn('403',health['error'])
 def test_end_to_end_report_generation_with_mock_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   (root/'sources.json').write_text(json.dumps({'sources':[SOURCE]}),encoding='utf-8')
   fake=(parse_rss(MOCK_RSS,SOURCE,T),{'source_id':SOURCE['id'],'group':'audio','status':'ok','items':1,'method':'rss'})
   with patch('collector.collect_one',return_value=fake):
    result=build('all','2026-11-25',root,workers=1)
   self.assertEqual(result['attempted_sources'],1)
   self.assertEqual(result['candidates_per_group']['audio'],1)
   self.assertEqual(result['overall_status'],'sources_fetched_not_fact_checked')
   self.assertTrue((root/'data'/'latest'/'manifest.json').exists())
   self.assertTrue((root/'data'/'news.sqlite').exists())
 def test_db_and_reports(self):
  items=parse_rss(MOCK_RSS,SOURCE,T)
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)
   con=connect_db(path/'db.sqlite')
   self.assertEqual(insert_items(con,items,T),1)
   self.assertEqual(insert_items(con,items,T),0)
   rows=query_group(con,'audio','2026-11-25')
   self.assertEqual(len(rows),1)
   self.assertEqual(write_report('audio','2026-11-25',rows,{'ok':1},path/'reports'),1)
   self.assertEqual(json.loads((path/'reports'/'audio.json').read_text())['items'][0]['date_jst'],'2026-11-25')
   con.close()

if __name__=='__main__':unittest.main()
