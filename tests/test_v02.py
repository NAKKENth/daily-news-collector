import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from collector import (iso_utc,parse_rss,collect_one,connect_db,insert_items,query_group,process_listings,snapshot_pages,enrich_item,build,write_report)
from quality import triage,organize,page_metadata
T='2026-11-25T06:00:00+00:00'
S={'id':'sample','group':'audio','topic':'tws','label':'Sample','domain':'example.org','homepage':'https://example.org','role':'specialist','kind':'rss','feed_url':'https://example.org/feed','tier':'core'}
def row(title,group='audio',topic='tws',url='https://example.org/a',**kw):
    return dict(id=kw.pop('id','test'),title=title,group=group,topic=topic,url=url,description=kw.pop('description',''),source='Sample',publisher='Sample',source_id='sample',source_role='specialist',published_utc='2026-11-24T06:00:00+00:00',date_jst='2026-11-24',timestamp_basis='source_feed_published',link_role='source_article',first_seen_utc=T,**kw)
class TestV02(unittest.TestCase):
 def test_metadata(self):
    m=page_metadata(b'<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-11-24T23:30:00-05:00","dateModified":"2026-11-25T12:00:00Z"}</script><link rel="canonical" href="/news/a">','https://example.org/a')
    self.assertEqual(m['canonical'],'https://example.org/news/a');self.assertEqual(iso_utc(m['datePublished']),'2026-11-25T04:30:00+00:00')
 def test_atom_update_not_publication(self):
    a=parse_rss(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Test</title><link href="https://example.org/a"/><updated>2026-11-24T00:00:00Z</updated></entry></feed>',S,T)
    self.assertEqual(a[0]['timestamp_basis'],'source_feed_updated')
 def test_more_than_25(self):
    xml='<rss><channel>'+''.join(f'<item><title>Item {i}</title><link>https://example.org/{i}</link><pubDate>Tue, 24 Nov 2026 08:00:00 GMT</pubDate></item>' for i in range(80))+'</channel></rss>'
    self.assertEqual(len(parse_rss(xml.encode(),S,T)),80)
 def test_motogp_out(self):self.assertEqual(triage(row('MotoGP news','motorsport','F1'))['triage'],'exclude')
 def test_phone_reclassified(self):self.assertEqual(triage(row('Huawei Mate X8 launched'))['group'],'pc_ai')
 def test_pedal_reclassified(self):self.assertEqual(triage(row('Launch Date Confirmed: Fanatec Podium Pedals GT','games_handhelds','racing_games'))['topic'],'peripherals')
 def test_dac_and_sale(self):
    self.assertEqual(triage(row('FiiO BTR25 portable DAC announced'))['topic'],'bluetooth_dac')
    self.assertEqual(triage(row('Headphones Black Friday sale'))['triage'],'exclude')
    self.assertEqual(triage(row('Fanatec Podium Pedals Launch Date confirmed for Black Friday','games_handhelds','racing_games'))['triage'],'priority')
 def test_ambiguous_retained(self):self.assertEqual(triage(row('New model from manufacturer'))['triage'],'review')
 def test_exact_url_global_dedup(self):
    a,b=organize([row('New earbuds announced'),row('New earbuds announced','pc_ai','smartphones')]);self.assertEqual(len(a),1);self.assertEqual(len(a[0]['sources']),2);self.assertEqual(len(b),2)
 def test_distinct_stages_preserved(self):
    a,_=organize([row('Earbuds X announced'),row('Earbuds X shipping',url='https://example.org/b')]);self.assertEqual(len(a),2)
 def test_unresolved_google(self):
    x=row('New earbuds');x.update(url='https://news.google.com/rss/articles/abc',link_role='discovery_link',timestamp_basis='google_news_index')
    with patch('collector.fetch',return_value=(b'<html></html>',x['url'])):r=enrich_item(x)
    self.assertEqual(r['link_role'],'discovery_link');self.assertEqual(r['enrichment'],'unresolved_discovery')
 def test_original_timestamp_overrides_index(self):
    x=row('New earbuds');x.update(url='https://news.google.com/rss/articles/abc',link_role='discovery_link',timestamp_basis='google_news_index')
    with patch('collector.fetch',return_value=(b'<meta property="article:published_time" content="2026-11-24T20:05:00Z">','https://example.org/article')):r=enrich_item(x)
    self.assertEqual(r['date_jst'],'2026-11-25');self.assertEqual(r['timestamp_basis'],'article_published');self.assertEqual(r['discovery_url'],x['url'])
 def test_listing_baseline(self):
    with tempfile.TemporaryDirectory() as d:
        con=connect_db(Path(d)/'db');x=row('Product');x.update(timestamp_basis='listing_seen',published_utc=None,date_jst=None)
        self.assertEqual(process_listings(con,[x],[],T),[])
        y=dict(x,id='b',url='https://example.org/b');self.assertEqual(len(process_listings(con,[x,y],[],T)),1);con.close()
 def test_snapshot_baseline_then_change(self):
    with tempfile.TemporaryDirectory() as d:
        con=connect_db(Path(d)/'db');s=dict(S,monitor_pages=[{'url':'https://example.org/help','selector':'main','label':'Help'}]);first=b'<main>'+b'limits '*30+b'</main>';second=first.replace(b'limits',b'features')
        with patch('collector.fetch',side_effect=[(first,'https://example.org/help'),(second,'https://example.org/help')]):
            a,h=snapshot_pages(con,[s],T);self.assertEqual(a,[]);self.assertEqual(h[0]['status'],'baseline');a,h=snapshot_pages(con,[s],T)
        self.assertEqual(len(a),1);self.assertIsNone(a[0]['date_jst']);con.close()
 def test_old_db_upgrade_and_richer_timestamp(self):
    with tempfile.TemporaryDirectory() as d:
        con=connect_db(Path(d)/'db');x=row('Item');insert_items(con,[x],T);y=dict(x,timestamp_basis='article_published',date_jst='2026-11-25',published_utc='2026-11-24T20:00:00+00:00');insert_items(con,[y],T);insert_items(con,[x],T)
        self.assertEqual(len(query_group(con,'audio','2026-11-25')),1);con.close()
 def test_no_silent_report_cap(self):
    with tempfile.TemporaryDirectory() as d:
        rows=[row('Product '+str(i),url=f'https://example.org/{i}',id=str(i)) for i in range(121)]
        write_report('audio','2026-11-24',rows,{},Path(d));payload=json.loads((Path(d)/'audio.json').read_text());self.assertEqual(len(payload['items']),121);self.assertEqual(len(list(Path(d).glob('audio_tws_*.md'))),3)
if __name__=='__main__':unittest.main()
