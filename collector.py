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
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

JST = ZoneInfo('Asia/Tokyo')
UTC = timezone.utc
USER_AGENT = 'DailyNewsCandidateCollector/1.0 (public-source research, contact: repository owner)'
MAX_PER_SOURCE = 25
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
        for el in elems[:MAX_PER_SOURCE*2]:
            title=simplify_html(node_text(el,'title'),250)
            link=node_text(el,'link')
            if not link:
                guid=el.find('guid')
                link=(guid.text or '').strip() if guid is not None else ''
            published=iso_utc(node_text(el,'pubDate','{http://purl.org/dc/elements/1.1/}date'))
            description=node_text(el,'description','{http://purl.org/rss/1.0/modules/content/}encoded')
            pub_el=el.find('source')
            publisher=(pub_el.text or '').strip() if pub_el is not None else source['label']
            found.append((title,link,published,description,publisher))
    elif name=='feed':
        ns='{http://www.w3.org/2005/Atom}'
        for el in root.findall(ns+'entry')[:MAX_PER_SOURCE*2]:
            title=simplify_html(node_text(el,ns+'title'),250)
            links=el.findall(ns+'link')
            link=next((x.attrib.get('href','') for x in links if x.attrib.get('rel','alternate')=='alternate'), '') or next((x.attrib.get('href','') for x in links if x.attrib.get('rel','') in ('','alternate')),'')
            published=iso_utc(node_text(el,ns+'published',ns+'updated'))
            description=node_text(el,ns+'summary',ns+'content')
            found.append((title,link,published,description,source['label']))
    else:
        raise ValueError('not an RSS/Atom feed: '+name)

    result=[]
    for title,url,published,description,publisher in found:
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
            'timestamp_basis':'google_news_index' if is_gnews else 'source_feed_published',
            'link_role':'discovery_link' if is_gnews else 'source_article',
            'first_seen_utc':retrieved_at,
        }
        result.append(item)
    return result[:MAX_PER_SOURCE]


def parse_gh_releases(raw,source,retrieved_at):
    out=[]
    for rel in raw[:50]:
        if rel.get('draft'):continue
        url=rel.get('html_url','')
        ts=iso_utc(rel.get('published_at'))
        if not canonical_url(url):continue
        name=rel.get('name') or rel.get('tag_name') or 'Release'
        out.append(dict(id=stable_id(url,source['group']),group=source['group'],topic=source['topic'],source_id=source['id'],source=source['label'],source_role='developer',title=name,url=canonical_url(url),publisher=source['repository'],description=simplify_html(rel.get('body','')),published_utc=ts,date_jst=local_day(ts),timestamp_basis='github_release_published',link_role='original',first_seen_utc=retrieved_at,prerelease=bool(rel.get('prerelease'))))
    return out[:MAX_PER_SOURCE]


def parse_gh_pulls(raw,source,retrieved_at):
    out=[]
    for pr in raw:
        merged=iso_utc(pr.get('merged_at'))
        if not merged: continue
        url=pr.get('html_url','')
        if not canonical_url(url):continue
        out.append(dict(id=stable_id(url,source['group']),group=source['group'],topic=source['topic'],source_id=source['id'],source=source['label'],source_role='developer',title='Merged PR #'+str(pr.get('number'))+': '+str(pr.get('title','')),url=canonical_url(url),publisher=source['repository'],description=simplify_html(pr.get('body','')),published_utc=merged,date_jst=local_day(merged),timestamp_basis='github_pr_merged',link_role='original',first_seen_utc=retrieved_at))
    return out[:MAX_PER_SOURCE]


def request_data(url, *, token=None, is_json=False):
    headers={'User-Agent':USER_AGENT,'Accept':'application/vnd.github+json' if is_json else 'application/rss+xml, application/atom+xml, application/xml;q=0.9'}
    if token and urlparse(url).netloc=='api.github.com':
        headers['Authorization']='Bearer '+token
        headers['X-GitHub-Api-Version']='2022-11-28'
    # Sequential retries handle temporary outages and 429/5xx. Never bypass authentication or paywalls.
    last=None
    for i in range(2):
        try:
            resp=requests.get(url,headers=headers,timeout=(7,17),allow_redirects=True)
            if resp.status_code in (429,500,502,503,504) and i==0:
                last=f'HTTP {resp.status_code}'; continue
            resp.raise_for_status()
            if len(resp.content)>4_000_000:raise ValueError('response over 4 MB safety limit')
            return resp.json() if is_json else resp.content
        except (requests.RequestException,ValueError) as e:
            last=str(e)[:250]
            if i==0:continue
    raise RuntimeError(last or 'request failed')


def source_endpoint(s):
    if s['kind']=='rss':return s['feed_url']
    if s['kind']=='news':
        q=s.get('query') or 'site:'+s['domain']+' when:4d'
        # Explicit site search generates *discovery candidates* only. Google News might omit articles.
        if not s.get('query') and s['topic'] in TOPIC_WORDS and s['role'] not in ('official','developer'):
            q+=' '+TOPIC_WORDS[s['topic']]
        locale=s.get('locale','en')
        args={'q':q,'hl':'ja','gl':'JP','ceid':'JP:ja'} if locale=='ja' else {'q':q,'hl':'en-US','gl':'US','ceid':'US:en'}
        return 'https://news.google.com/rss/search?'+urlencode(args)
    if s['kind']=='github_releases':return 'https://api.github.com/repos/'+s['repository']+'/releases?per_page=50'
    if s['kind']=='github_merged_pr':return 'https://api.github.com/repos/'+s['repository']+'/pulls?state=closed&sort=updated&direction=desc&per_page=80'
    return None


def collect_one(s,retrieved_at, token):
    url=source_endpoint(s)
    if not url:
        return [],{'source_id':s['id'],'group':s['group'],'status':'manual','items':0,'note':'not accessible by open RSS/GitHub API'}
    try:
        raw=request_data(url,token=token,is_json=s['kind'].startswith('github_'))
        if s['kind']=='github_releases': items=parse_gh_releases(raw,s,retrieved_at)
        elif s['kind']=='github_merged_pr':items=parse_gh_pulls(raw,s,retrieved_at)
        else:items=parse_rss(raw,s,retrieved_at)
        cutoff=now_utc()-timedelta(days=MAX_AGE_DAYS)
        items=[x for x in items if not x['published_utc'] or datetime.fromisoformat(x['published_utc'])>=cutoff]
        return items,{'source_id':s['id'],'group':s['group'],'status':'ok' if items else 'empty','items':len(items),'method':s['kind']}
    except Exception as ex:
        primary_error=str(ex)[:180]
        if s['kind']=='rss':
            # A broken or blocked primary RSS doesn't become a silent "no news".
            # Site-scoped Google News lookup is only a degraded discovery fallback.
            fallback=dict(s,kind='news')
            try:
                raw=request_data(source_endpoint(fallback),token=None,is_json=False)
                items=parse_rss(raw,fallback,retrieved_at)
                cutoff=now_utc()-timedelta(days=MAX_AGE_DAYS)
                items=[x for x in items if not x['published_utc'] or datetime.fromisoformat(x['published_utc'])>=cutoff]
                status='fallback' if items else 'fallback_empty'
                return items,{'source_id':s['id'],'group':s['group'],'status':status,'items':len(items),'method':'google_news_fallback','primary_error':primary_error}
            except Exception as exc2:
                return [],{'source_id':s['id'],'group':s['group'],'status':'failed','items':0,'method':s['kind'],'error':'RSS: '+primary_error+'; fallback: '+str(exc2)[:100]}
        return [],{'source_id':s['id'],'group':s['group'],'status':'failed','items':0,'method':s['kind'],'error':primary_error}


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
            con.execute('UPDATE articles SET last_seen_utc=?,description=CASE WHEN length(description)<length(?) THEN ? ELSE description END WHERE id=?',(retrieved_at,i['description'],i['description'],i['id']))
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


def write_report(group,date,rows,health,out_dir):
    out_dir.mkdir(parents=True,exist_ok=True)
    date_rows=[x for x in rows if x['date_jst']==date]
    unknown=[x for x in rows if not x['date_jst']]
    items={'date_jst':date,'group':group,'title':GROUP_TITLES[group],
           'status':'candidate_collection_only','items':[{k:x[k] for k in ('id','topic','title','url','source','publisher','description','published_utc','date_jst','timestamp_basis','link_role','date_quality')} for x in date_rows],
           'date_unknown':[{'title':x['title'],'url':x['url'],'source':x['source'],'first_seen_utc':x['first_seen_utc']} for x in unknown[:30]],
           'health':health}
    (out_dir/f'{group}.json').write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text=[f'# {GROUP_TITLES[group]}｜{date} JST の記事候補','',
          '**自動収集された候補です。重要度・原典・実際の出来事の日付は未検証。**',
          '検索発見リンク（Google News）は元記事の代わりではありません。原典を探し直してください。','',
          f'収録候補：{len(date_rows)}件／日時不明：{len(unknown)}件／取得結果：直接成功{health.get("ok",0)}・検索代替{health.get("fallback",0)}・0件{health.get("empty",0)}・失敗{health.get("failed",0)}・未実行{health.get("skipped",0)}','']
    grouped=defaultdict(list)
    for x in date_rows: grouped[x['topic']].append(x)
    # Preserve topic diversity; the full JSON and SQLite retain all candidates.
    topics_total = max(1,len(grouped))
    budget_per_topic = max(14,160 // topics_total)
    for topic,topic_rows in grouped.items():
        text.extend([f'## {topic}（全{len(topic_rows)}件／下記最大{budget_per_topic}件）',''])
        for x in topic_rows[:budget_per_topic]:
            local=datetime.fromisoformat(x['published_utc']).astimezone(JST).strftime('%m/%d %H:%M') if x['published_utc'] else '不明'
            basis={'github_release_published':'GitHubリリース公開','github_pr_merged':'GitHub PRマージ','source_feed_published':'元媒体RSS記事日時','google_news_index':'Google News配信日時・原典要確認'}.get(x['timestamp_basis'],'日時不明')
            text.append(f'- [{markdown_escape(x["title"])}]({x["url"]}) — {markdown_escape(x["source"])}｜{local} JST｜{basis}')
        text.append('')
    if unknown:
        text.extend(['## 日時未確定（当日分には算入しない）',''])
        for x in unknown[:30]:text.append(f'- [{markdown_escape(x["title"])}]({x["url"]}) — {x["source"]}')
    if health.get('failed',0):
        text.extend(['','## 取得失敗（収集できた候補ゼロと混同しない）',''])
        for s in health.get('failed_sources',[]):text.append(f'- {s}')
    (out_dir/f'{group}.md').write_text('\n'.join(text).rstrip()+'\n',encoding='utf-8')
    return len(date_rows)


def build(scoped='all',target_date=None,root=PATH_ROOT,workers=7):
    cfg=json.loads((root/'sources.json').read_text(encoding='utf-8'))
    all_sources=cfg['sources']
    if target_date is None:target_date=(datetime.now(JST).date()-timedelta(days=1)).isoformat()
    datetime.fromisoformat(target_date)
    selected=[s for s in all_sources if s['kind']!='manual' and (scoped=='all' or s['tier']=='core')]
    retrieved_at=now_utc().isoformat(timespec='seconds')
    token=os.environ.get('GITHUB_TOKEN','')
    results=[];health=[]
    with ThreadPoolExecutor(max_workers=max(1,min(workers,10))) as pool:
        futures=[pool.submit(collect_one,s,retrieved_at,token) for s in selected]
        for f in as_completed(futures):
            items,h=f.result();results.extend(items);health.append(h)
    selected_ids={x['id'] for x in selected}
    for s in all_sources:
        if s['id'] not in selected_ids:
            health.append({'source_id':s['id'],'group':s['group'],'status':'manual' if s['kind']=='manual' else 'skipped','items':0})
    db=connect_db(root/'data'/'news.sqlite')
    added=insert_items(db,results,retrieved_at)
    db.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?)',(retrieved_at,scoped,sum(h['status'] in ('ok','fallback') for h in health),sum(h['status'] in ('empty','fallback_empty') for h in health),sum(h['status']=='failed' for h in health),sum(h['status'] in ('skipped','manual') for h in health),added,json.dumps(health,ensure_ascii=False)))
    db.commit()
    report=root/'data'/'latest'
    counts={}
    for group in GROUP_ORDER:
        hs=[x for x in health if x['group']==group]
        stat={k:sum(x['status']==k for x in hs) for k in ('ok','empty','fallback','fallback_empty','failed','skipped','manual')}
        stat['failed_sources']=[x['source_id']+': '+x.get('error','')[:65] for x in hs if x['status']=='failed']
        counts[group]=write_report(group,target_date,query_group(db,group,target_date),stat,report)
    state={
        'generated_at_utc':retrieved_at,'target_date_jst':target_date,'scope':scoped,
        'catalog_sources':len(all_sources),'attempted_sources':len(selected),
        'status_counts':dict(Counter(x['status'] for x in health)),
        'new_unique_articles':added,'candidates_per_group':counts,
        'overall_status':'partial' if any(x['status'] in ('failed','fallback','fallback_empty') for x in health) else 'sources_fetched_not_fact_checked',
        'source_health':sorted(health,key=lambda x:x['source_id'])}
    report.mkdir(parents=True,exist_ok=True)
    (report/'manifest.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (report/'README.md').write_text('# 前日ニュース候補 '+target_date+' JST\n\n'+'\n'.join(f'- [{GROUP_TITLES[g]}]({g}.md)：{c}件' for g,c in counts.items())+'\n\nこの索引は収集候補であり、ニュース記事の正確性や網羅性の保証ではありません。詳細な失敗一覧は manifest.json を参照。\n',encoding='utf-8')
    db.close()
    print(json.dumps({k:state[k] for k in ('target_date_jst','scope','attempted_sources','status_counts','new_unique_articles','candidates_per_group','overall_status')},ensure_ascii=False,indent=2))
    return state


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--scope',choices=['core','all'],default='all')
    p.add_argument('--date',help='Target JST day YYYY-MM-DD (default: yesterday JST)')
    p.add_argument('--workers',type=int,default=7)
    args=p.parse_args()
    build(args.scope,args.date,PATH_ROOT,args.workers)

if __name__=='__main__':main()
