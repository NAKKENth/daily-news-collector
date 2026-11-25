"""Upgrade v0.1 catalog in place, retaining existing source IDs and custom entries."""
import json,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FEEDS={
'motorsport-motorsport-jp':'https://jp.motorsport.com/rss/all/news/',
'motorsport-motorsport-en-f1':'https://www.motorsport.com/rss/f1/news/',
'pc_ai-techpowerup':'https://www.techpowerup.com/rss/news',
'pc_ai-akiba-pc-hotline':'https://akiba-pc.watch.impress.co.jp/data/rss/1.0/ah/feed.rdf',
'pc_ai-videocardz':'https://feeds.feedburner.com/VideoCardzcom',
}
# Candidate URLs are tried and parsed at runtime; unavailable endpoints fall back.
CANDIDATES={
'pc_ai-tftcentral':['https://tftcentral.co.uk/feed'],
'pc_ai-igor’slab':['https://www.igorslab.de/en/feed/'],
'pc_ai-testingcatalog':['https://www.testingcatalog.com/rss/'],
'pc_ai-helentech':['https://helentech.jp/feed/'],
'motorsport-racefans':['https://www.racefans.net/feed/'],
'motorsport-rallit':['https://www.rallit.fi/feed/'],
'motorsport-rallyjournal':['https://rallyjournal.com/feed/'],
'motorsport-wrcwings':['https://www.wrcwings.tech/feed/'],
'motorsport-autoracer':['https://autoracer.it/feed/'],
'motorsport-sportscar365':['https://sportscar365.com/feed/'],
'games_handhelds-retro-game-corps':['https://retrogamecorps.com/feed/'],
'games_handhelds-retro-dodo':['https://retrododo.com/feed/'],
'games_handhelds-traxion':['https://traxion.gg/feed/'],
'audio-the-walkman-blog':['https://thewalkmanblog.blogspot.com/feeds/posts/default?alt=rss'],
'audio-soundguys':['https://www.soundguys.com/feed/'],
'audio-scarbir':['https://www.scarbir.com/tws?format=rss'],
'audio-linsoul':['https://www.linsoul.com/blogs/news.atom'],
'audio-hifigo':['https://hifigo.com/blogs/news.atom'],
'audio-shenzhenaudio':['https://shenzhenaudio.com/blogs/news.atom'],
}
# Official stores/listings: first observation is not evidence of release. Later new links are candidates.
LISTINGS={
'audio-linsoul':['https://www.linsoul.com/blogs/news','https://www.linsoul.com/'],
'audio-hifigo':['https://hifigo.com/collections/new-arrivals'],
'audio-shenzhenaudio':['https://shenzhenaudio.com/'],
'audio-musicteck':['https://musicteck.com/'],
'audio-dunu':['https://www.dunu-topsound.com/'],
'audio-moondrop':['https://moondroplab.com/'],
'audio-fiio':['https://www.fiio.com/'],
'audio-ibasso':['https://ibasso.com/'],
'audio-shanling':['https://en.shanling.com/'],
'games_handhelds-retroid':['https://www.goretroid.com/'],
'games_handhelds-ayn':['https://www.ayn.hk/'],
'games_handhelds-ayaneo':['https://www.ayaneo.com/'],
'games_handhelds-anbernic':['https://anbernic.com/'],
'games_handhelds-powkiddy':['https://powkiddy.com/'],
'games_handhelds-trimui':['https://www.trimui.com/'],
}
MONITORS={
'pc_ai-openai-help':[{'url':'https://help.openai.com/en/articles/6825453-chatgpt-release-notes','selector':'article','label':'ChatGPT Release Notes'},{'url':'https://openai.com/chatgpt/pricing/','selector':'main','label':'ChatGPT plan/pricing'},{'url':'https://help.openai.com/en/articles/9624314-model-release-notes','selector':'article','label':'Model Release Notes'},{'url':'https://help.openai.com/en/articles/20001625-understanding-chatgpt-and-codex-usage-limits','selector':'article','label':'ChatGPT/Codex usage limits'}],
'pc_ai-claude-help':[{'url':'https://support.claude.com/en/articles/12138966-release-notes','selector':'article','label':'Claude Release Notes'},{'url':'https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work','selector':'article','label':'Claude usage limits'}],
'pc_ai-google-ai':[{'url':'https://support.google.com/gemini/answer/16275805?hl=en','selector':'main','label':'Gemini Apps limits & feature availability'}],
}
JP={'motorsport-motorsport-jp','motorsport-autosport-web','motorsport-rally-plus','motorsport-super-formula-official','motorsport-super-gt-official','pc_ai-akiba-pc-hotline','pc_ai-helentech','pc_ai-itmedia-mobile','pc_ai-nichepcgamer','audio-e-earphone','audio-phile-web','audio-aviot','games_handhelds-azur-lane-jp','games_handhelds-yostar-jp'}
LOCALES={'motorsport-amus':'de','motorsport-rallit':'fi','motorsport-autoracer':'it','motorsport-formulapassion':'it','pc_ai-igor’slab':'de','pc_ai-benchlife':'zh-TW'}
def upgrade(cfg):
 for s in cfg['sources']:
  k=s['id']
  if k in FEEDS:s.update(kind='rss',feed_url=FEEDS[k])
  if k in CANDIDATES:s.update(feed_candidates=CANDIDATES[k],direct_discovery=True)
  elif s['kind']=='news' and s['role']!='official':s['direct_discovery']=True
  if k in LISTINGS:s.update(listing_urls=LISTINGS[k],search_supplement=True,tier='core')
  if k in MONITORS:s.update(monitor_pages=MONITORS[k],tier='core')
  if k in JP:s['locale']='ja'
  if k in LOCALES:s['locale']=LOCALES[k]
  # collect existing broad domains by narrower topic where applicable
  if k=='motorsport-sky-sports-f1':s['query']='site:skysports.com/f1 when:4d'
  if k=='motorsport-f1technical':s['query']='site:f1technical.net when:4d (F1 OR Formula 1)'
  if k=='games_handhelds-valve-steam-deck':s['query']='site:store.steampowered.com when:4d ("Steam Deck" OR SteamOS)'
  if k=='audio-apple-airpods':s['query']='site:apple.com when:4d (AirPods OR Beats OR "audio")'
 cfg['schema_version']=2
 return cfg
if __name__=='__main__':
 p=ROOT/'sources.json';cfg=upgrade(json.loads(p.read_text(encoding='utf-8')));p.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 with (ROOT/'sources_catalog.csv').open('w',encoding='utf-8-sig',newline='') as f:
  fields=['id','group','label','topic','kind','tier','role','domain','homepage','feed_url','feed_candidates','listing_urls','monitor_pages','locale','query','direct_discovery','search_supplement','repository','note','include_any'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
  for s in cfg['sources']:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in s.items()})
 print('Sources:',len(cfg['sources']))
