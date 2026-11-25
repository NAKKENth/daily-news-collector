"""Add direct public routes to existing IDs; candidate URLs are runtime validated."""
import json,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FEEDS={
'pc_ai-openai':['https://openai.com/news/rss.xml'],
'pc_ai-google-ai':['https://blog.google/feed/'],
'pc_ai-google-deepmind':['https://deepmind.google/blog/rss.xml'],
'pc_ai-ars-technica':['https://feeds.arstechnica.com/arstechnica/index'],
'pc_ai-techcrunch':['https://techcrunch.com/feed/'],
'pc_ai-wccftech':['https://wccftech.com/feed/'],
'pc_ai-the-verge':['https://www.theverge.com/rss/index.xml'],
'audio-sony-audio':['https://www.sony.net/SonyInfo/News/Press/data/pressrelease_for_top.xml'],
'games_handhelds-joey-retro-handhelds':['https://joeysretrohandhelds.com/feed/'],
'motorsport-formulapassion':['https://www.formulapassion.it/feed'],
'motorsport-rally-plus':['https://www.rallyplus.net/feed'],
'pc_ai-hardware-busters':['https://hwbusters.com/feed/'],
'pc_ai-storagereview':['https://www.storagereview.com/feed'],
'pc_ai-nichepcgamer':['https://www.nichepcgamer.com/feed'],
'audio-l7audiolab':['https://www.l7audiolab.com/feed/'],
'games_handhelds-onexplayer':['https://onexplayerstore.com/blogs/news.atom'],
'games_handhelds-retroid':['https://www.goretroid.com/blogs/news.atom'],
'audio-qudelix':['https://www.qudelix.com/blogs/5k-dac-amp.atom'],
'audio-oneplus-audio':['https://www.oneplus.com/blog/rss.xml'],
}
LISTINGS={
'pc_ai-anthropic':['https://www.anthropic.com/news'],
'pc_ai-openai':['https://openai.com/news/'],
'pc_ai-google-ai':['https://blog.google/innovation-and-ai/technology/ai/'],
'pc_ai-google-deepmind':['https://deepmind.google/blog/'],
'games_handhelds-onexplayer':['https://onexplayerstore.com/blogs/news','https://onexplayerstore.com/collections/all'],
'games_handhelds-retroid':['https://www.goretroid.com/collections/all'],
'games_handhelds-ayn':['https://www.ayn.hk/collections/all'],
'games_handhelds-azur-lane-jp':['https://azurlane.jp/'],
'audio-qudelix':['https://www.qudelix.com/'],
'audio-questyle':['https://www.questyle.com/'],
'audio-nothing':['https://nothing.tech/'],
'audio-aviot':['https://aviot.jp/'],
}
FILTERS={'audio-sony-audio':['earbuds','headphone','headset','earphone','イヤホン','ヘッドホン','le audio','auracast'], 'pc_ai-google-ai':['gemini','deepmind','notebooklm','artificial intelligence',' ai ','生成ai','aiモデル']}
def upgrade(cfg):
    for s in cfg['sources']:
        k=s['id']
        if k in FEEDS:
            s['direct_discovery']=True;s['feed_candidates']=list(dict.fromkeys(FEEDS[k]+s.get('feed_candidates',[])))
        if k in LISTINGS:
            s['listing_urls']=list(dict.fromkeys(LISTINGS[k]+s.get('listing_urls',[])));s['tier']='core'
        if k in FILTERS:s['include_any']=FILTERS[k]
        # Narrow Google News to newsroom; store/support pages are not launch announcements.
        if k=='audio-apple-airpods':
            s['query']='site:apple.com/newsroom (AirPods OR Beats OR earbuds OR headphones) when:4d'
            s['search_supplement']=False
        if k=='pc_ai-openai-help':
            s['query']='site:help.openai.com (ChatGPT OR Codex) (limits OR plan OR release OR pricing) when:4d'
            p={'url':'https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus','selector':'article, main, [role="main"]','label':'ChatGPT Plus plan (代替監視)','required_terms':['Plus']}
            if not any(m['url']==p['url'] for m in s['monitor_pages']):s['monitor_pages'].append(p)
        # For direct feeds, avoid obligatory duplicate search on specialist sources.
        if k in ('games_handhelds-retro-handhelds',):s['search_supplement']=False
    return cfg
if __name__=='__main__':
    p=ROOT/'sources.json';cfg=upgrade(json.loads(p.read_text(encoding='utf-8')));p.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (ROOT/'sources_catalog.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=list(dict.fromkeys(k for s in cfg['sources'] for k in s));w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for s in cfg['sources']:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in s.items()})
