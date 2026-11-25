import tempfile, unittest, json, time
from pathlib import Path
from unittest.mock import patch, Mock
import collector as c
from quality import triage, organize
from test_v02 import S,T,row

def source(g,i):return dict(S,id=f'{g}-{i}',group=g,kind='news',tier='core')
def h(s):return dict(source_id=s['id'],group=s['group'],search_needed=True,direct_methods=[],status='failed',items=0,errors=[],error='',hit_cap=False)
class TestV021(unittest.TestCase):
 def setUp(self):
    c.NEWS_BLOCKED=False;c.NEWS_RETRY_EPOCH=0;c.NEWS_LAST=0
 def test_fair_rotation(self):
    src=[source(g,i) for g in c.GROUP_ORDER for i in range(3)]
    self.assertEqual([x['group'] for x in c.fair_order(src)[:4]],list(c.GROUP_ORDER))
    self.assertEqual(c.fair_order(src,rotation=3)[0]['group'],'audio')
 def test_pending_before_recent(self):
    a,b=source('audio',1),source('audio',2)
    self.assertEqual(c.fair_order([a,b],{a['id']:(10,10,0),b['id']:(20,0,1)})[0],b)
 def test_search_budget_persists(self):
    with tempfile.TemporaryDirectory() as d:
      db=c.connect_db(Path(d)/'db');src=[source(g,i) for g in c.GROUP_ORDER for i in range(2)];health=[h(s) for s in src]
      with patch('collector.request_data',return_value=b'<rss><channel/></rss>') as req:
        self.assertEqual(c.search_pass(db,src,health,[],T,4,0),4);self.assertEqual(req.call_count,4)
      self.assertEqual(sum(x['status']=='deferred' for x in health),4)
      self.assertEqual(db.execute('SELECT count(*) FROM search_state WHERE pending=1').fetchone()[0],4);db.close()
 def test_rate_limit_halts_search_only(self):
    with tempfile.TemporaryDirectory() as d:
      db=c.connect_db(Path(d)/'db');src=[source(g,1) for g in c.GROUP_ORDER];health=[h(s) for s in src]
      def fail(*a,**k):c.NEWS_BLOCKED=True;c.NEWS_RETRY_EPOCH=time.time()+3600;raise RuntimeError('429')
      with patch('collector.request_data',side_effect=fail) as req:
        self.assertEqual(c.search_pass(db,src,health,[],T,48,3),1);self.assertEqual(req.call_count,1)
      self.assertEqual(health[-1]['status'],'failed');self.assertEqual(sum(x['status']=='deferred' for x in health),3)
      self.assertGreater(float(db.execute("SELECT value FROM collector_state WHERE key='news_retry_epoch'").fetchone()[0]),time.time());db.close()
 def test_actual_429_respects_retry_after(self):
    import requests
    resp=requests.Response();resp.status_code=429;resp.url='https://news.google.com/rss/search';resp.headers['Retry-After']='7200';resp._content=b'';resp._content_consumed=True
    with patch('collector.safe_public_url'),patch('collector.requests.get',return_value=resp) as get:
      with self.assertRaises(RuntimeError):c.fetch(resp.url)
      self.assertEqual(get.call_count,1);self.assertTrue(c.NEWS_BLOCKED);self.assertGreater(c.NEWS_RETRY_EPOCH-time.time(),7100)
 def test_empty_direct_rss_not_search(self):
    with patch('collector.request_data',return_value=b'<rss><channel/></rss>'):
      _,health=c.collect_one(S,T,'',True);self.assertFalse(health['search_needed']);self.assertEqual(health['status'],'empty')
 def test_listing_multi_endpoint_partial(self):
    s=dict(S,listing_urls=['https://example.org/a','https://example.org/b'])
    with patch('collector.fetch',side_effect=[(b'<a href="/product-page/new">New earbuds model</a>','https://example.org/a'),RuntimeError('403')]):
      xs,errors=c.direct_listing(s,T)
    self.assertEqual(len(xs),1);self.assertEqual(len(errors),1);self.assertIsNone(xs[0]['date_jst'])
 def test_listing_new_endpoint_has_own_baseline(self):
    with tempfile.TemporaryDirectory() as d:
      db=c.connect_db(Path(d)/'db');x=row('Product');x.update(timestamp_basis='listing_seen',published_utc=None,date_jst=None,listing_endpoint='https://example.org/one')
      self.assertEqual(c.process_listings(db,[x],[],T),[])
      y=dict(x,url='https://example.org/b',listing_endpoint='https://example.org/two')
      self.assertEqual(c.process_listings(db,[y],[],T),[])
      z=dict(y,url='https://example.org/c');self.assertEqual(len(c.process_listings(db,[y,z],[],T)),1);db.close()
 def test_monitor_semantic_fallback(self):
    with tempfile.TemporaryDirectory() as d:
      db=c.connect_db(Path(d)/'db');s=dict(S,monitor_pages=[dict(url='https://example.org/help',selector='main, article',label='Gemini limits',required_terms=['Gemini','limits'])]);raw=b'<main>Wrong content</main><article>'+b'Gemini limits '*20+b'</article>'
      with patch('collector.fetch',return_value=(raw,'https://example.org/help')):
        _,health=c.snapshot_pages(db,[s],T);self.assertEqual(health[0]['status'],'baseline')
      db.close()
 def test_jobs_not_news(self):self.assertEqual(triage(row('Sr. Product SCAN Engineer in Austin, Texas | AMD','pc_ai','pc'))['triage'],'exclude')
 def test_event_hints_keep_evidence(self):
    a=row('Nothing unveils Ear (note) earbuds',url='https://example.org/a');b=row('Nothing announces Ear Note earbuds',url='https://example.org/b');d=row('Nothing Ear Note shipping',url='https://example.org/c');xs,_=organize([a,b,d]);self.assertEqual(len(xs),3);self.assertEqual(xs[0]['possible_event_id'],xs[1]['possible_event_id']);self.assertNotIn('possible_event_id',xs[2])
if __name__=='__main__':unittest.main()
