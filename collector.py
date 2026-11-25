#!/usr/bin/env python3
"""Four-lane public-source news candidate collector.
Does not claim that a feed timestamp equals the original event date or that a hit is newsworthy.
The ChatGPT editor must verify individual source links before summarizing.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import threading
import ipaddress
import socket
from urllib.parse import urljoin
from quality import organize, page_metadata, title_key, triage
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

JST = ZoneInfo('Asia/Tokyo')
UTC = timezone.utc
USER_AGENT = 'DailyNewsCandidateCollector/2.0 (public-source research, contact: repository owner)'
MAX_PER_SOURCE = 100
MAX_PAGES = 3
NEWS_LOCK = threading.Lock()
NEWS_LAST = 0.0
NEWS_PAUSE_UNTIL = 0.0
NEWS_INTERVAL = 1.2
NEWS_BLOCKED = False
NEWS_429_COUNT = 0
MAX_AGE_DAYS = 5
PATH_ROOT = Path(__file__).resolve().parent
TOPIC_WORDS = {
    'ai': '(AI OR Gemini OR Claude OR ChatGPT OR OpenAI OR model)',
    'smartphones': '(smartphone OR Android OR Pixel OR phone)',
    'handhelds': '(handheld OR Retroid OR AYANEO OR ANBERNIC OR Linux OR Steam Deck)',
    'racing_games': '("racing game" OR "Assetto Corsa" OR Forza OR iRacing OR Gran Turismo OR WRC OR racing)',
    'azur_lane': '("Azur Lane" OR アズールレーン)',
    'peripherals': '(controller OR wheel OR peripheral OR gamepad OR FFB)',
    'portable_dac': '(DAC OR USB audio OR headphone amp)',
    'bluetooth_dac': '(DAC OR Bluetooth OR receiver)',
    'tws': '(earbuds OR TWS OR headphones OR AirPods OR Bluetooth)',
}
TRACKER_QUERY = {'utm_source','utm_medium','utm_campaign','utm_content','utm_term','fbclid','gclid','ref','source','campaign'}
GROUP_ORDER = ('motorsport','pc_ai','games_handhelds','audio')
GROUP_TITLES = {'motorsport':'モータースポーツ','pc_ai':'PC・AI・スマートフォン','games_handhelds':'ゲーム・ハンドヘルド','audio':'オーディオ'}


def now_utc():
    return datetime.now(UTC)


def iso_utc(value):
    """Convert RSS/Atom/GitHub timestamps to UTC ISO strings; None if unknown."""
    if value is None or not str(value).strip():
        return None
    try:
        t = datetime.fromisoformat(str(value).strip().replace('Z','+00:00'))
    except (TypeError, ValueError):
        try:
            t = parsedate_to_datetime(str(value))
        except (TypeError, ValueError, IndexError):
            return None
    if t.tzinfo is None:
        return None  # no timezone: cannot assign a JST publication day safely
    return t.astimezone(UTC).isoformat(timespec='seconds')


def local_day(iso):
    if not iso:
        return None
    return datetime.fromisoformat(iso).astimezone(JST).strftime('%Y-%m-%d')


def canonical_url(url):
    if not isinstance(url,str):
        return ''
    p = urlparse(url.strip())
    if p.scheme not in ('https','http') or not p.netloc:
        return ''
    host = p.netloc.lower()
    cleanq = [(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k.lower() not in TRACKER_QUERY and not k.lower().startswith('utm_')]
    path = re.sub('/+', '/', p.path).rstrip('/') or '/'
    return urlunparse((p.scheme,host,path,'',urlencode(cleanq),'')).strip()


def stable_id(url, group=""):
    # Same story can legitimately be relevant to multiple independent briefing lanes.
    return hashlib.sha256((group+"|"+canonical_url(url)).encode('utf-8')).hexdigest()[:24]


def node_text(el, *names):
    for n in names:
        v = el.findtext(n)
        if v and v.strip():return v.strip()
    # RDF/RSS 1.0 titles and links are commonly namespace-qualified.
    local_names={x.rsplit('}',1)[-1] for x in names}
    for child in el:
        if child.tag.rsplit('}',1)[-1] in local_names and child.text and child.text.strip():
            return child.text.strip()
    return ''


def simplify_html(s,limit=350):
    t = BeautifulSoup(s or '', 'html.parser').get_text(' ', strip=True)
    return re.sub(r'\s+', ' ', t).strip()[:limit]


def parse_rss(xml_bytes, source, retrieved_at):
    """Parse RSS 2.0 or Atom safely; do not fetch external entities."""
    root = ET.fromstring(xml_bytes)
    name = root.tag.rsplit('}',1)[-1].lower()
    found=[]
    if name == 'rss' or name=='rdf':
        elems=[el for el in root.iter() if el.tag.rsplit('}',1)[-1]=='item']
        for el in elems[:500]:
            title=simplify_html(node_text(el,'title'),250)
            link=node_text(el,'link')
            if not link:
                guid=el.find('guid')
                link=(guid.text or '').strip() if guid is not None else ''
            published=iso_utc(node_text(el,'pubDate','{http://purl.org/dc/elements/1.1/}date'))
            description=node_text(el,'description','{http://purl.org/rss/1.0/modules/content/}encoded')
            pub_el=el.find('source')
            publisher=(pub_el.text or '').strip() if pub_el is not None else source['label']
            found.append((title,link,published,description,publisher,'source_feed_published'))
    elif name=='feed':
        ns='{http://www.w3.org/2005/Atom}'
        for el in root.findall(ns+'entry')[:500]:
            title=simplify_html(node_text(el,ns+'title'),250)
            links=el.findall(ns+'link')
            link=next((x.attrib.get('href','') for x in links if x.attrib.get('rel','alternate')=='alternate'), '') or next((x.attrib.get('href','') for x in links if x.attrib.get('rel','') in ('','alternate')),'')
            published=iso_utc(node_text(el,ns+'published'))
            updated=iso_utc(node_text(el,ns+'updated'))
            if not published and updated: published=updated
            description=node_text(el,ns+'summary',ns+'content')
            found.append((title,link,published,description,source['label'],'source_feed_published' if node_text(el,ns+'published') else 'source_feed_updated'))
    else:
        raise ValueError('not an RSS/Atom feed: '+name)

    result=[]
    for title,url,published,description,publisher,basis in found:
        url=canonical_url(url)
        if not title or not url:
            continue
        include_any=source.get('include_any') or []
        if include_any and not any(w.casefold() in (title+' '+simplify_html(description)).casefold() for w in include_any):
            continue
        is_gnews=source['kind']=='news'
        item={
            'id':stable_id(url,source['group']),'group':source['group'],'topic':source['topic'],
            'source_id':source['id'],'source':source['label'],'source_role':source['role'],
            'title':title,'url':url,'publisher':publisher or source['label'],
            'description':simplify_html(description),
            'published_utc':published,'date_jst':local_day(published),
            'timestamp_basis':'google_news_index' if is_gnews else basis,
            'link_role':'discovery_link' if is_gnews else 'source_article',
            'first_seen_utc':retrieved_at,
        }
        result.append(item)
    return result


def parse_gh_releases(raw,source,retrieved_at):
    out=[]
    for rel in raw:
        if rel.get('draft'):continue
        url=rel.get('html_url','')
        ts=iso_utc(rel.get('published_at'))
        if not canonical_url(url):continue
        name=rel.get('name') or rel.get('tag_name') or 'Release'
        out.append(dict(id=stable_id(url,source['group']),group=source['group'],topic=source['topic'],source_id=source['id'],source=source['label'],source_role='developer',title=name,url=canonical_url(url),publisher=source['repository'],description=simplify_html(rel.get('body','')),published_utc=ts,date_jst=local_day(ts),timestamp_basis='github_release_published',link_role='original',first_seen_utc=retrieved_at,prerelease=bool(rel.get('prerelease'))))
    return out


def parse_gh_pulls(raw,source,retrieved_at):
    out=[]
    for pr in raw:
        merged=iso_utc(pr.get('merged_at'))
        if not merged: continue
        url=pr.get('html_url','')
        if not canonical_url(url):continue
        out.append(dict(id=stable_id(url,source['group']),group=source['group'],topic=source['topic'],source_id=source['id'],source=source['label'],source_role='developer',title='Merged PR #'+str(pr.get('number'))+': '+str(pr.get('title','')),url=canonical_url(url),publisher=source['repository'],description=simplify_html(pr.get('body','')),published_utc=merged,date_jst=local_day(merged),timestamp_basis='github_pr_merged',link_role='original',first_seen_utc=retrieved_at))
    return out


def safe_public_url(url):
    p=urlparse(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.port not in (None,80,443):raise ValueError('unsafe URL')
    # Public URLs only. Re-check each redirect, do not pass tokens to other hosts.
    for info in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(info[4][0]).is_global:raise ValueError('non-public address')
    return url


def fetch(url, *, token=None, accept='*/*', is_news=False):
    global NEWS_LAST, NEWS_PAUSE_UNTIL, NEWS_BLOCKED, NEWS_429_COUNT
    last=None
    for i in range(3):
        try:
            u=url
            for _ in range(6):
                safe_public_url(u)
                headers={'User-Agent':USER_AGENT,'Accept':accept}
                if token and urlparse(u).hostname=='api.github.com':
                    headers.update(Authorization='Bearer '+token, **{'X-GitHub-Api-Version':'2022-11-28'})
                if urlparse(u).hostname=='news.google.com':
                    with NEWS_LOCK:
                        if NEWS_BLOCKED:raise ValueError('Google News circuit open after repeated 429; retry next scheduled run')
                        time.sleep(max(0,NEWS_LAST+NEWS_INTERVAL-time.monotonic(),NEWS_PAUSE_UNTIL-time.monotonic()))
                        NEWS_LAST=time.monotonic()
                        resp=requests.get(u,headers=headers,timeout=(6,15),allow_redirects=False,stream=True)
                        if resp.status_code==429:
                            try: delay=float(resp.headers.get('Retry-After','8'))
                            except ValueError:delay=8
                            NEWS_429_COUNT+=1
                            if delay>60 or NEWS_429_COUNT>=3:NEWS_BLOCKED=True
                            NEWS_PAUSE_UNTIL=time.monotonic()+max(8,delay)
                        elif resp.ok:NEWS_429_COUNT=0
                else:
                    resp=requests.get(u,headers=headers,timeout=(6,15),allow_redirects=False,stream=True)
                with resp:
                    if resp.is_redirect and resp.headers.get('Location'):
                        u=urljoin(u,resp.headers['Location']);continue
                    resp.raise_for_status()
                    chunks=[];n=0
                    for chunk in resp.iter_content(65536):
                        n+=len(chunk)
                        if n>5_000_000:raise ValueError('response over 5 MB')
                        chunks.append(chunk)
                    return b''.join(chunks),u
            raise ValueError('too many redirects')
        except (requests.RequestException,ValueError,OSError) as e:
            last=str(e)[:250]
            status=getattr(getattr(e,'response',None),'status_code',None)
            if status in (401,403,404,410) or isinstance(e,ValueError):break
            if i<2:time.sleep(2**i*2)
    raise RuntimeError(last or 'request failed')


def request_data(url, *, token=None, is_json=False):
    raw,_=fetch(url,token=token,accept='application/vnd.github+json' if is_json else 'application/rss+xml, application/atom+xml, application/xml;q=0.9')
    return json.loads(raw) if is_json else raw


def discover_feed(s):
    # Try explicitly configured feed, then HTML-declared RSS/Atom (not guessed URLs).
    for candidate in s.get('feed_candidates',[]):
        try:return request_data(candidate),candidate
        except Exception:pass
    home=s.get('homepage')
    if not home:raise RuntimeError('no homepage')
    raw,final=fetch(home,accept='text/html')
    soup=BeautifulSoup(raw,'html.parser')
    links=[urljoin(final,x['href']) for x in soup.find_all('link',href=True) if x.get('type') in ('application/rss+xml','application/atom+xml','application/rdf+xml')]
    for candidate in list(dict.fromkeys(links))[:2]:
        try:
            data=request_data(candidate); ET.fromstring(data); return data,candidate
        except Exception:pass
    raise RuntimeError('no usable declared feed')


def direct_listing(s,retrieved_at):
    # Only explicitly configured public listing URLs; keep unknown dates unknown.
    out=[]
    for endpoint in s.get('listing_urls',[]):
        raw,final=fetch(endpoint,accept='text/html')
        soup=BeautifulSoup(raw,'html.parser')
        for a in soup.select('article a[href], main h2 a[href], main h3 a[href], a[href*="/blogs/"], a[href*="/products/"]'):
            u=canonical_url(urljoin(final,a.get('href','')));title=simplify_html(a.get_text(' ',strip=True),250)
            if not title or len(title)<8 or not u or urlparse(u).hostname!=urlparse(final).hostname or u==canonical_url(final):continue
            if '/blogs/' in u and len(urlparse(u).path.strip('/').split('/'))<3:continue
            out.append(dict(id=stable_id(u,s['group']),group=s['group'],topic=s['topic'],source_id=s['id'],source=s['label'],source_role=s['role'],title=title,url=u,publisher=s['label'],description='',published_utc=None,date_jst=None,timestamp_basis='listing_seen',link_role='listing_candidate',first_seen_utc=retrieved_at))
    if not out:raise RuntimeError('listing selector found no candidate links')
    return list({x['url']:x for x in out}.values())[:MAX_PER_SOURCE]


def source_endpoint(s):
    if s['kind']=='rss':return s['feed_url']
    if s['kind']=='news':
        q=s.get('query') or 'site:'+s['domain']+' when:4d'
        # Explicit site search generates *discovery candidates* only. Google News might omit articles.
        if not s.get('query') and s['topic'] in TOPIC_WORDS:
            q+=' '+TOPIC_WORDS[s['topic']]
        locale=s.get('locale','en')
        lang,region={'ja':('ja','JP'),'de':('de','DE'),'fi':('fi','FI'),'it':('it','IT'),'zh-TW':('zh-TW','TW')}.get(locale,('en-US','US'));args={'q':q,'hl':lang,'gl':region,'ceid':region+':'+('en' if locale=='en' else lang)}
        return 'https://news.google.com/rss/search?'+urlencode(args)
    if s['kind']=='github_releases':return 'https://api.github.com/repos/'+s['repository']+'/releases?per_page=100'
    if s['kind']=='github_merged_pr':return 'https://api.github.com/repos/'+s['repository']+'/pulls?state=closed&sort=updated&direction=desc&per_page=100'
    return None


def collect_one(s,retrieved_at, token):
    url=source_endpoint(s)
    base={'source_id':s['id'],'group':s['group']}
    if not url:return [],dict(base,status='manual',items=0)
    items=[];errors=[];methods=[]
    def add(xs,method):
        items.extend(xs);methods.append(method)
    if s['kind'].startswith('github_'):
        try:
            for page in range(1,MAX_PAGES+1):
                raw=request_data(url+'&page='+str(page),token=token,is_json=True)
                parser=parse_gh_releases if s['kind']=='github_releases' else parse_gh_pulls
                add(parser(raw,s,retrieved_at),s['kind'])
                if len(raw)<100:break
                dates=[iso_utc(x.get('updated_at') or x.get('published_at')) for x in raw]
                if all(d and datetime.fromisoformat(d)<datetime.fromisoformat(retrieved_at)-timedelta(days=MAX_AGE_DAYS) for d in dates):break
            else:errors.append('GitHub page cap reached; older rows may be missing')
        except Exception as e:errors.append(str(e)[:200])
    else:
        if s['kind']=='rss':
            try:add(parse_rss(request_data(url),s,retrieved_at),'rss')
            except Exception as e:errors.append('RSS: '+str(e)[:150])
        elif s.get('direct_discovery'):
            try:
                raw,endpoint=discover_feed(s)
                add(parse_rss(raw,dict(s,kind='rss'),retrieved_at),'rss_discovered')
            except Exception as e:errors.append('direct RSS: '+str(e)[:140])
        if s.get('listing_urls'):
            try:add(direct_listing(s,retrieved_at),'listing')
            except Exception as e:errors.append('listing: '+str(e)[:140])
        # Search is a fallback, or an explicitly requested supplement for product sources.
        if not methods or not items or s.get('search_supplement'):
            try:
                fallback=dict(s,kind='news'); add(parse_rss(request_data(source_endpoint(fallback)),fallback,retrieved_at),'news')
            except Exception as e:errors.append('search: '+str(e)[:160])
    cutoff=datetime.fromisoformat(retrieved_at)-timedelta(days=MAX_AGE_DAYS)
    items=[x for x in items if not x['published_utc'] or datetime.fromisoformat(x['published_utc'])>=cutoff]
    # Preserve richer direct observations over duplicate URLs.
    dedup={}
    for x in items:
        if x['url'] not in dedup or dedup[x['url']]['link_role']=='discovery_link':dedup[x['url']]=x
    items=list(dedup.values())
    status=('failed' if not methods else ('partial' if errors else ('ok' if items else 'empty')))
    return items,dict(base,status=status,items=len(items),method='+'.join(dict.fromkeys(methods)) or s['kind'],errors=errors,error='; '.join(errors)[:500],hit_cap=len(items)>=MAX_PER_SOURCE)


def enrich_item(x):
    """Resolve only normal public redirects; Google interstitials remain discovery-only."""
    x=dict(x)
    if x['timestamp_basis'].startswith('github_') or x['timestamp_basis']=='page_change_observed':return x
    old=x['url']
    try:
        raw,final=fetch(old,accept='text/html,application/xhtml+xml')
        if urlparse(final).hostname in ('news.google.com','consent.google.com','accounts.google.com'):
            x['enrichment']='unresolved_discovery';return x
        m=page_metadata(raw,final)
        # Only same-domain canonical, and never replace an article by a homepage.
        can=canonical_url(m['canonical']);f=canonical_url(final)
        if not can or urlparse(can).hostname!=urlparse(f).hostname or urlparse(can).path=='/':can=f
        if not can or urlparse(can).path=='/':x['enrichment']='not_article';return x
        x['discovery_url']=old if x['link_role']=='discovery_link' and old!=can else x.get('discovery_url')
        x['url']=can;x['id']=stable_id(can,x['group']);x['link_role']='source_article'
        x['article_published_raw']=m.get('datePublished');x['article_modified_raw']=m.get('dateModified')
        if m.get('description'):x['description']=m['description']
        if m.get('headline'):x['title']=m['headline'][:250]
        published=iso_utc(m.get('datePublished'))
        if published:
            x['published_utc']=published;x['date_jst']=local_day(published);x['timestamp_basis']='article_published'
        # A resolved Google URL with no article time keeps discovery date only.
        x['enrichment']='article_metadata' if published else 'url_only'
    except Exception as e:x['enrichment']='failed';x['enrichment_error']=str(e)[:160]
    return x


def connect_db(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path)
    con.execute('PRAGMA journal_mode=DELETE')
    con.execute('''CREATE TABLE IF NOT EXISTS articles(
        id TEXT PRIMARY KEY, group_name TEXT, topic TEXT, source_id TEXT,
        source TEXT, source_role TEXT, title TEXT, url TEXT, publisher TEXT,
        description TEXT, published_utc TEXT, date_jst TEXT, timestamp_basis TEXT,
        link_role TEXT, first_seen_utc TEXT, last_seen_utc TEXT, metadata TEXT)''')
    con.execute('CREATE INDEX IF NOT EXISTS articles_group_date ON articles(group_name,date_jst)')
    con.execute('''CREATE TABLE IF NOT EXISTS runs(run_time_utc TEXT PRIMARY KEY, scope TEXT,
        successes INTEGER, empties INTEGER, failures INTEGER, skipped INTEGER, new_items INTEGER, status_json TEXT)''')
    con.execute('CREATE TABLE IF NOT EXISTS listing_seen(source_id TEXT,url TEXT,first_seen_utc TEXT,PRIMARY KEY(source_id,url))')
    con.execute('CREATE TABLE IF NOT EXISTS listing_baselines(source_id TEXT PRIMARY KEY,observed_utc TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS page_snapshots(url TEXT PRIMARY KEY, digest TEXT, observed_utc TEXT)')
    con.commit()
    return con


def insert_items(con,items,retrieved_at):
    added=0
    for i in items:
        meta={k:v for k,v in i.items() if k not in {'id','group','topic','source_id','source','source_role','title','url','publisher','description','published_utc','date_jst','timestamp_basis','link_role','first_seen_utc'}}
        row=(i['id'],i['group'],i['topic'],i['source_id'],i['source'],i['source_role'],i['title'],i['url'],i['publisher'],i['description'],i['published_utc'],i['date_jst'],i['timestamp_basis'],i['link_role'],retrieved_at,retrieved_at,json.dumps(meta,ensure_ascii=False))
        before=con.total_changes
        con.execute('''INSERT OR IGNORE INTO articles(id,group_name,topic,source_id,source,source_role,title,url,publisher,description,published_utc,date_jst,timestamp_basis,link_role,first_seen_utc,last_seen_utc,metadata)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',row)
        if con.total_changes>before:added+=1
        else:
            old,oldmeta=con.execute('SELECT timestamp_basis,metadata FROM articles WHERE id=?',(i['id'],)).fetchone()
            try:oldmeta=json.loads(oldmeta or '{}')
            except ValueError:oldmeta={}
            if 'enrichment' not in meta and oldmeta.get('enrichment'):meta={**oldmeta,**meta}
            rank={'article_published':4,'github_release_published':4,'github_pr_merged':4,'source_feed_published':3,'source_feed_updated':2,'google_news_index':1,'listing_seen':0}
            if rank.get(i['timestamp_basis'],0)>=rank.get(old,0):
                con.execute('UPDATE articles SET title=?,description=?,published_utc=?,date_jst=?,timestamp_basis=?,link_role=?,metadata=?,last_seen_utc=? WHERE id=?',(i['title'],i['description'],i['published_utc'],i['date_jst'],i['timestamp_basis'],i['link_role'],json.dumps(meta,ensure_ascii=False),retrieved_at,i['id']))
            else:con.execute('UPDATE articles SET last_seen_utc=? WHERE id=?',(retrieved_at,i['id']))
    con.commit()
    return added


def query_group(con,group,target_date):
    con.row_factory=sqlite3.Row
    a=con.execute('''SELECT * FROM articles WHERE group_name=? AND (date_jst=? OR (date_jst IS NULL AND substr(first_seen_utc,1,10) >= ?)) ORDER BY CASE WHEN date_jst=? THEN 0 ELSE 1 END,published_utc DESC,first_seen_utc DESC''',(group,target_date,(datetime.fromisoformat(target_date)-timedelta(days=2)).date().isoformat(),target_date)).fetchall()
    result=[]
    for x in a:
        d=dict(x)
        d['date_quality']='github_event' if d['timestamp_basis'].startswith('github_') else ('feed_published' if d['timestamp_basis']=='source_feed_published' else ('discovery_index' if d['timestamp_basis']=='google_news_index' else 'unknown'))
        result.append(d)
    return result


def markdown_escape(s):
    return (s or '').replace('\\','\\\\').replace('[','\\[').replace(']','\\]').replace('\n',' ')


def row_dict(x):
    d=dict(x)
    if d.get('metadata'):
        try:d.update(json.loads(d['metadata']))
        except ValueError:pass
    d.pop('metadata',None);d['group']=d.get('group',d.get('group_name'))
    basis=d.get('timestamp_basis','')
    d['date_quality']={'article_published':'article_metadata','source_feed_published':'feed_published','source_feed_updated':'updated_only','google_news_index':'discovery_index','listing_seen':'unknown','page_change_observed':'observed_change'}.get(basis,'github_event' if basis.startswith('github_') else 'unknown')
    return d


def write_report(group,date,rows,health,out_dir):
    out_dir.mkdir(parents=True,exist_ok=True)
    rows=[row_dict(x) for x in rows];active=[x for x in rows if x.get('triage')!='exclude']
    date_rows=[x for x in active if x.get('date_jst')==date]
    unknown=[x for x in active if not x.get('date_jst')]
    def short(x):
        keys=('id','topic','title','url','source','publisher','description','published_utc','date_jst','timestamp_basis','link_role','date_quality','triage','triage_reason','possible_event_id','sources','discovery_url','article_published_raw','article_modified_raw','enrichment','prerelease')
        return {k:x[k] for k in keys if k in x}
    payload={'schema_version':2,'date_jst':date,'group':group,'title':GROUP_TITLES[group],'status':'candidate_collection_only','items':[short(x) for x in date_rows],'date_unknown':[short(x) for x in unknown],'health':health}
    (out_dir/f'{group}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # All candidates available. Compact per-topic shards avoid context truncation; no silent cap.
    grouped=defaultdict(list)
    for x in date_rows+unknown:grouped[x['topic']].append(x)
    lines=[f'# {GROUP_TITLES[group]}｜{date} JST 候補（v0.2）','候補のみ。記事の日時・出来事・重要度は要検証。検索索引時刻・更新時刻・観測時刻は正式発表時刻ではない。',f'日付付き候補 {len(date_rows)}件／日時不明 {len(unknown)}件。全文はJSON・下記の分割ファイル。','']
    for topic,rs in sorted(grouped.items()):
        safe=re.sub(r'[^A-Za-z0-9_-]','_',topic)
        rs.sort(key=lambda x:(x.get('triage')!='priority',x.get('date_jst')!=date,x.get('link_role')=='discovery_link',x.get('title','')))
        for ix in range(0,len(rs),50):
            shard=f'{group}_{safe}_{ix//50+1}.md'
            text=[f'# {topic} / {date} / 候補 {ix+1}–{min(ix+50,len(rs))}','']
            for x in rs[ix:ix+50]:
                q=x.get('date_quality','unknown'); label='優先' if x.get('triage')=='priority' else '要確認'
                text.append(f'- [{markdown_escape(x["title"])}]({x["url"]}) — {x.get("source","")}｜{label}｜{x.get("published_utc") or "日時不明"} UTC｜{q}'+(f'｜同一話題候補 {x["possible_event_id"]}' if x.get('possible_event_id') else ''))
            (out_dir/shard).write_text('\n'.join(text)+'\n',encoding='utf-8')
            lines.append(f'- [{topic} {ix+1}–{min(ix+50,len(rs))}件]({shard})')
    (out_dir/f'{group}.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return len(date_rows)


def process_listings(db, results, health, retrieved_at):
    by_source=defaultdict(list); out=[]
    for x in results:
        if x['timestamp_basis']=='listing_seen':by_source[x['source_id']].append(x)
        else:out.append(x)
    for sid,rs in by_source.items():
        baseline=db.execute('SELECT 1 FROM listing_baselines WHERE source_id=?',(sid,)).fetchone()
        for x in rs:
            exists=db.execute('SELECT 1 FROM listing_seen WHERE source_id=? AND url=?',(sid,x['url'])).fetchone()
            db.execute('INSERT OR IGNORE INTO listing_seen VALUES(?,?,?)',(sid,x['url'],retrieved_at))
            if baseline and not exists:
                x['description']='公式・販売店の一覧で新たに観測したリンク。発表・発売日は未確定。'
                out.append(x)
        db.execute('INSERT OR IGNORE INTO listing_baselines VALUES(?,?)',(sid,retrieved_at))
        for h in health:
            if h['source_id']==sid:h['listing_baseline_created']=not bool(baseline)
    db.commit();return out


def snapshot_pages(db, selected, retrieved_at):
    out=[]; health=[]
    for source in selected:
        for m in source.get('monitor_pages',[]):
            status={'source_id':source['id'],'url':m['url']}
            try:
                raw,final=fetch(m['url'],accept='text/html');soup=BeautifulSoup(raw,'html.parser');node=soup.select_one(m['selector'])
                if not node:raise ValueError('monitor selector not found')
                for n in node.select('script,style,nav,footer,header,button'):n.decompose()
                text=re.sub(r'\s+',' ',node.get_text(' ',strip=True)).strip()
                if len(text)<100:raise ValueError('monitor text too short')
                digest=hashlib.sha256(text.encode()).hexdigest();prev=db.execute('SELECT digest,observed_utc FROM page_snapshots WHERE url=?',(m['url'],)).fetchone()
                if prev and prev[0]!=digest:
                    # Change observed between scans; not a confirmed feature change or publication date.
                    link=canonical_url(m['url']);out.append(dict(id=hashlib.sha256((link+digest).encode()).hexdigest()[:24],group=source['group'],topic=source['topic'],source_id=source['id'],source=source['label'],source_role=source['role'],title=m['label']+'：ページ変更を観測（要差分確認）',url=link,publisher=source['label'],description='前回観測 '+prev[1]+' → 今回観測 '+retrieved_at+'。変更内容・発生日は未確定。',published_utc=None,date_jst=None,timestamp_basis='page_change_observed',link_role='monitor_page',first_seen_utc=retrieved_at))
                db.execute('INSERT OR REPLACE INTO page_snapshots VALUES(?,?,?)',(m['url'],digest,retrieved_at));status['status']='baseline' if not prev else 'changed' if prev[0]!=digest else 'unchanged'
            except Exception as e:status.update(status='failed',error=str(e)[:160])
            health.append(status)
    db.commit();return out,health


def build(scoped='all',target_date=None,root=PATH_ROOT,workers=7,enrich_limit=100):
    cfg=json.loads((root/'sources.json').read_text(encoding='utf-8'));all_sources=cfg['sources']
    if target_date is None:target_date=(datetime.now(JST).date()-timedelta(days=1)).isoformat()
    datetime.fromisoformat(target_date);retrieved_at=now_utc().isoformat(timespec='seconds');token=os.environ.get('GITHUB_TOKEN','')
    db=connect_db(root/'data'/'news.sqlite')
    previous=db.execute('SELECT status_json FROM runs ORDER BY run_time_utc DESC LIMIT 1').fetchone()
    prior=json.loads(previous[0]) if previous else []
    retry_ids={x['source_id'] for x in prior if x['status'] in ('failed','partial') or x.get('previous_status') in ('failed','partial')}
    selected=[s for s in all_sources if s['kind']!='manual' and (scoped=='all' or (scoped=='core' and s['tier']=='core') or s['id'] in retry_ids)]
    results=[];health=[]
    with ThreadPoolExecutor(max_workers=max(1,min(workers,8))) as pool:
        for f in as_completed([pool.submit(collect_one,s,retrieved_at,token) for s in selected]):
            items,h=f.result();results.extend(items);health.append(h)
    for s in all_sources:
        if s['id'] not in {x['id'] for x in selected}:health.append({'source_id':s['id'],'group':s['group'],'status':'manual' if s['kind']=='manual' else 'skipped','items':0})
    # Retry list is persisted by source; do not discard last known failure just because scope skipped it.
    prior_map={x['source_id']:x for x in prior}
    for h in health:
        if h['status']=='skipped' and h['source_id'] in prior_map:h['previous_status']=prior_map[h['source_id']].get('previous_status',prior_map[h['source_id']]['status'])
    results=process_listings(db,results,health,retrieved_at)
    monitored,monitor_health=snapshot_pages(db,selected,retrieved_at)
    results.extend(monitored)
    added=insert_items(db,results,retrieved_at)
    # Enrich target-day and unknown candidates with fair per-group round-robin. Persist raw observations first.
    db.row_factory=sqlite3.Row
    candidates=[row_dict(x) for x in db.execute('SELECT * FROM articles WHERE date_jst=? OR (date_jst IS NULL AND first_seen_utc>=?)',(target_date,(datetime.fromisoformat(target_date)-timedelta(days=2)).date().isoformat()))]
    by_title=defaultdict(list)
    for x in candidates:
        if x['link_role']!='discovery_link':by_title[title_key(x)].append(x)
    # Exact same title + same publisher: link to existing direct observation, never guess URL.
    mapped=[]
    for x in candidates:
        if x['link_role']!='discovery_link':continue
        matches=[y for y in by_title.get(title_key(x),[]) if y.get('publisher','').casefold()==x.get('publisher','').casefold() and len(title_key(x))>=20]
        if len({y['url'] for y in matches})==1:
            y=matches[0];z=dict(x,url=y['url'],id=stable_id(y['url'],x['group']),published_utc=y['published_utc'],date_jst=y['date_jst'],timestamp_basis=y['timestamp_basis'],link_role=y['link_role'],discovery_url=x['url'],enrichment='feed_title_match');mapped.append(z)
    # Preserve original discovery URLs; exact matches are suppressed only in curated view.
    enriched=[];queues=defaultdict(list);already={x['discovery_url'] for x in mapped}
    for x in candidates:
        t=triage(x)
        if t['triage']=='exclude' or (x['timestamp_basis'].startswith('github_') or x['timestamp_basis']=='page_change_observed') or x['url'] in already or x.get('enrichment') in ('article_metadata','url_only','feed_title_match','unresolved_discovery'):continue
        if x['link_role']=='source_article' and x['timestamp_basis']=='source_feed_published':continue
        queues[t['group']].append((t['triage']!='priority',x))
    for q in queues.values():q.sort(key=lambda z:(z[0],z[1].get('enrichment')=='failed',z[1].get('url','')))
    chosen=[]
    while len(chosen)<enrich_limit and any(queues.values()):
        for g in GROUP_ORDER:
            if queues[g] and len(chosen)<enrich_limit:chosen.append(queues[g].pop(0)[1])
    with ThreadPoolExecutor(max_workers=4) as pool:
        enriched=list(pool.map(enrich_item,chosen))
    insert_items(db,mapped+enriched,retrieved_at)
    db.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?)',(retrieved_at,scoped,sum(h['status']=='ok' for h in health),sum(h['status']=='empty' for h in health),sum(h['status'] in ('failed','partial') for h in health),sum(h['status'] in ('skipped','manual') for h in health),added,json.dumps(health,ensure_ascii=False)));db.commit()
    rows=[row_dict(x) for x in db.execute('SELECT * FROM articles WHERE date_jst=? OR (date_jst IS NULL AND first_seen_utc>=?)',(target_date,(datetime.fromisoformat(target_date)-timedelta(days=2)).date().isoformat()))]
    # If verified metadata moved a candidate to another day, suppress its stale discovery copy too.
    resolved={row_dict(x).get('discovery_url') for x in db.execute("SELECT * FROM articles WHERE last_seen_utc>=?",((datetime.fromisoformat(target_date)-timedelta(days=5)).date().isoformat(),)) if row_dict(x).get('enrichment') in ('article_metadata','url_only','feed_title_match')}
    active,raw=organize([x for x in rows if x['url'] not in resolved])
    report=root/'data'/'latest';report.mkdir(parents=True,exist_ok=True)
    for stale in report.glob('*.md'):
        if any(stale.name.startswith(g+'_') for g in GROUP_ORDER):stale.unlink()
    counts={};audit={}
    (report/'triage_audit.json').write_text(json.dumps([{'id':x['id'],'group':x['group'],'topic':x['topic'],'title':x['title'],'url':x['url'],'triage':x['triage'],'reason':x['triage_reason']} for x in active if x['triage']=='exclude'],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for group in GROUP_ORDER:
        hs=[x for x in health if x['group']==group];stat=dict(Counter(x['status'] for x in hs))
        gr=[x for x in active if x['group']==group]
        counts[group]=write_report(group,target_date,gr,stat,report)
        audit[group]=dict(Counter(x['triage'] for x in gr))
    # Keep raw candidate database, publish short audit instead of full page content.
    state={'schema_version':2,'generated_at_utc':retrieved_at,'target_date_jst':target_date,'scope':scoped,'catalog_sources':len(all_sources),'attempted_sources':len(selected),'status_counts':dict(Counter(x['status'] for x in health)),'new_unique_articles':added,'candidates_per_group':counts,'triage_counts':audit,'raw_target_rows':len(rows),'curated_rows':len(active),'enrichment_attempted':len(chosen),'enrichment_counts':dict(Counter(x.get('enrichment','unknown') for x in enriched+mapped)),'overall_status':'partial' if any(x['status'] in ('failed','partial','skipped') for x in health) or any(x['status']=='failed' for x in monitor_health) else 'sources_fetched_not_fact_checked','monitor_health':monitor_health,'source_health':sorted(health,key=lambda x:x['source_id'])}
    (report/'manifest.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (report/'README.md').write_text('# 前日ニュース候補 '+target_date+' JST｜v0.2\n\n'+'\n'.join(f'- [{GROUP_TITLES[g]}]({g}.md)：{c}件' for g,c in counts.items())+'\n\n候補であり確認済みニュースではありません。manifest.jsonで収集状態を確認。\n',encoding='utf-8')
    db.close();print(json.dumps({k:v for k,v in state.items() if k!='source_health'},ensure_ascii=False,indent=2));return state


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--scope',choices=['core','all','retry'],default='all')
    p.add_argument('--date',help='Target JST day YYYY-MM-DD (default: yesterday JST)')
    p.add_argument('--workers',type=int,default=7)
    p.add_argument('--enrich-limit',type=int,default=80,help='Max candidate article fetches per run')
    args=p.parse_args()
    build(args.scope,args.date,PATH_ROOT,args.workers,args.enrich_limit)

if __name__=='__main__':main()
