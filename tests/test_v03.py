import json, sqlite3, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import collector as c
from archive_v03 import coverage,publish
from quality import organize,triage
from test_v02 import row,T

class TestV03(unittest.TestCase):
 def setup_db(self,d):
    db=c.connect_db(Path(d)/'data'/'news.sqlite');db.row_factory=sqlite3.Row;return db
 def archive(self,db,d,target,stamp,resolved=()):
    return publish(db,Path(d)/'data',target,stamp,set(resolved),c.row_dict,organize,c.write_report,[])
 def test_late_candidate_cross_day(self):
    with tempfile.TemporaryDirectory() as d:
      db=self.setup_db(d);old=row('New earbuds A announced',url='https://example.org/a',id='a');c.insert_items(db,[old],T)
      self.archive(db,d,'2026-11-24',T)
      stamp='2026-11-26T01:00:00+00:00';new=dict(old,id='b',url='https://example.org/b',title='New earbuds B announced');c.insert_items(db,[new],stamp)
      r=self.archive(db,d,'2026-11-25',stamp);self.assertEqual(r['audio'],1)
      p=Path(d)/'data';a=json.loads((p/'archive/2026-11-24/audio.json').read_text());self.assertEqual(len(a['items']),2)
      late=json.loads((p/'latest/audio_recovery.json').read_text())['items'];self.assertEqual(late[0]['date_jst'],'2026-11-24');self.assertEqual(late[0]['url'],new['url'])
      self.archive(db,d,'2026-11-25','2026-11-26T02:00:00+00:00');self.assertEqual(db.execute('SELECT count(*) FROM late_candidates').fetchone()[0],1);db.close()
 def test_old_archive_baseline_no_false_recovery(self):
    with tempfile.TemporaryDirectory() as d:
      db=self.setup_db(d);c.insert_items(db,[row('New earbuds announced')],T);self.assertEqual(self.archive(db,d,'2026-11-25','2026-11-26T02:00:00+00:00')['audio'],0);db.close()
 def test_archive_date_correction_removes_stale_candidate(self):
    with tempfile.TemporaryDirectory() as d:
      db=self.setup_db(d);self.archive(db,d,'2026-11-24',T);x=row('New earbuds announced');c.insert_items(db,[x],T);self.archive(db,d,'2026-11-25',T)
      y=dict(x,date_jst='2026-11-25',published_utc='2026-11-24T20:00:00+00:00',timestamp_basis='article_published');c.insert_items(db,[y],T);self.assertEqual(self.archive(db,d,'2026-11-25',T)['audio'],0);db.close()
 def test_coverage_keeps_success_across_deferred(self):
    with tempfile.TemporaryDirectory() as d:
      db=self.setup_db(d);a={'source_id':'a','group':'audio','status':'ok','direct_methods':['rss'],'search_status':'ok'};coverage(db,[a],T)
      db.execute('INSERT INTO search_state VALUES (?,?,?,?)',('a',0,0,1));b=dict(a,status='deferred',direct_methods=[],search_status='deferred_rate_limit');r=coverage(db,[b],'2026-11-25T14:00:00+00:00');self.assertEqual(r['sources'][0]['last_direct_ok'],T);self.assertTrue(r['sources'][0]['search_pending']);self.assertEqual(r['sources'][0]['last_status'],'deferred');db.close()
 def test_403_cooldown_other_host_still_works(self):
    c.ENRICH_BLOCKED_HOSTS.clear();a=row('New earbuds announced');b=dict(a,url='https://example.org/b');d=dict(a,url='https://other.example/a')
    try:
      with patch('collector.fetch',side_effect=[RuntimeError('403 Forbidden'),(b'<meta property="article:published_time" content="2026-11-24T20:00:00Z">',d['url'])]) as fetch:
        self.assertEqual(c.enrich_item(a)['enrichment'],'failed');self.assertEqual(c.enrich_item(b)['enrichment'],'deferred_host');self.assertEqual(c.enrich_item(d)['enrichment'],'article_metadata');self.assertEqual(fetch.call_count,2)
    finally:c.ENRICH_BLOCKED_HOSTS.clear()
 def test_noise_filters_keep_real_news(self):
    for title in ['Use your Beats 360 - Apple Support','iPad - Beats Headphones - Beats Accessories - Apple','King James Bible Audio - KJV - Apple','HEGEL、フルアナログ構成のプリメイン「A200」。DACやデジタル入力を省く','AudioQuest、スピーカーケーブル発表']:
      x=row(title);x['timestamp_basis']='google_news_index';self.assertEqual(triage(x)['triage'],'exclude',title)
    self.assertEqual(triage(row('EarFun、Boseと共同でANCを強化した完全ワイヤレス「Air Pro 5」。来年1月登場'))['triage'],'priority')
 def test_http_https_same_title_dedup(self):
    a=row('A &amp; B earbuds announced',url='http://example.org/a');b=row('A & B earbuds announced',url='https://example.org/a');xs,_=organize([a,b]);self.assertEqual(len(xs),1);self.assertEqual(xs[0]['url'],b['url']);self.assertEqual(len(xs[0]['sources']),2)
 def test_catalog_ids_unchanged(self):
    from catalog_v03 import upgrade
    cfg=json.loads((Path(c.__file__).parent/'sources.json').read_text());ids=[s['id'] for s in cfg['sources']];upgrade(cfg);self.assertEqual(ids,[s['id'] for s in cfg['sources']]);self.assertEqual(len(ids),168);self.assertEqual(len(set(ids)),168)
if __name__=='__main__':unittest.main()
