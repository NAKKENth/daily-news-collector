"""Add targeted public endpoints to v0.2 without replacing custom sources or IDs.
URLs are discovery candidates, not guaranteed accessible on Actions runners.
"""
import json,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FEEDS={
'audio-apple-airpods':['https://www.apple.com/newsroom/rss-feed.rss'],
'audio-samsung-audio':['https://news.samsung.com/global/category/press-resources/press-release/feed'],
'audio-musicteck':['https://shop.musicteck.com/blogs/news.atom'],
'audio-xmems':['https://xmems.com/feed/'],
'audio-bluetooth-sig':['https://www.bluetooth.com/feed/'],
'audio-l7audiolab':['https://www.l7audiolab.com/feed/'],
'audio-sammobile':['https://www.sammobile.com/feed/'],
}
LISTINGS={
'audio-fiio':['https://www.fiio.com/fiionews'],
'audio-dunu':['https://www.dunu-topsound.com/category/new-arrivals','https://www.dunu-topsound.com/category/all-products'],
'audio-shanling':['https://en.shanling.com/news'],
'audio-musicteck':['https://shop.musicteck.com/collections/new-arrivals'],
'audio-earfun':['https://www.myearfun.com/eu/press-release'],
'audio-linsoul':['https://www.linsoul.com/blogs/news'],
'audio-apple-airpods':['https://www.apple.com/newsroom/'],
'audio-samsung-audio':['https://news.samsung.com/global/'],
}
FILTERS={
'audio-apple-airpods':['airpods','beats','headphone','earbud','hearing','le audio'],
'audio-samsung-audio':['galaxy buds','earbud','headphone','le audio','auracast'],
'audio-sammobile':['galaxy buds','earbud','headphone','le audio','auracast'],
}
def upgrade(cfg):
 for s in cfg['sources']:
  k=s['id']
  if k in FEEDS:
   s['direct_discovery']=True;s['feed_candidates']=list(dict.fromkeys(FEEDS[k]+s.get('feed_candidates',[])))
  if k in LISTINGS:
   s['listing_urls']=list(dict.fromkeys(LISTINGS[k]+s.get('listing_urls',[])));s['tier']='core';s['search_supplement']=True
  if k in FILTERS:s['include_any']=FILTERS[k]
  if s['group']=='audio' and s['kind']=='news' and s['role'] in ('official','retailer'):
   s['direct_discovery']=True
  if k=='audio-aviot':s['locale']='ja'
  if k=='pc_ai-google-ai':
   for m in s.get('monitor_pages',[]):m.update(selector='article, .article-container, .article-content, main, [role="main"]',required_terms=['Gemini','limits'])
  if k=='pc_ai-openai-help':
   for m in s.get('monitor_pages',[]):
    if 'pricing' in m['url']:m.update(url='https://chatgpt.com/pricing/',selector='main, [role="main"], article, #main',required_terms=['Plus','Pro'])
  if k=='games_handhelds-retro-handhelds':s['search_supplement']=True
 return cfg
if __name__=='__main__':
 p=ROOT/'sources.json';cfg=upgrade(json.loads(p.read_text(encoding='utf-8')));p.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 with (ROOT/'sources_catalog.csv').open('w',encoding='utf-8-sig',newline='') as f:
  fields=list(dict.fromkeys(k for s in cfg['sources'] for k in s));w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for s in cfg['sources']:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in s.items()})
