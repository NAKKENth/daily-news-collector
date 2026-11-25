"""Rolling candidate archives, late discovery journal, and source coverage ledger.
No delivery acknowledgement: recovered candidates can recur in the rolling window.
"""
from collections import Counter
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

GROUPS=('motorsport','pc_ai','games_handhelds','audio')
JST=ZoneInfo('Asia/Tokyo')
def dump(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def coverage(db,health,stamp):
    db.execute('CREATE TABLE IF NOT EXISTS source_coverage(source_id TEXT PRIMARY KEY, group_name TEXT, last_attempt TEXT, last_direct_ok TEXT, last_search_ok TEXT, last_status TEXT)')
    # Replay previous run history on migration, then update with current health.
    if not db.execute('SELECT 1 FROM source_coverage LIMIT 1').fetchone():
        for ts,raw in db.execute('SELECT run_time_utc,status_json FROM runs ORDER BY run_time_utc').fetchall():
            _update(db,json.loads(raw),ts)
    _update(db,health,stamp);db.commit()
    fields=('source_id','group','last_attempt','last_direct_ok','last_search_ok','last_status')
    rows=[dict(zip(fields,r)) for r in db.execute('SELECT * FROM source_coverage ORDER BY source_id')]
    cutoff=(datetime.fromisoformat(stamp)-timedelta(hours=24)).isoformat()
    pending={r[0] for r in db.execute('SELECT source_id FROM search_state WHERE pending=1')}
    for r in rows:
        r['search_pending']=r['source_id'] in pending
        r['successful_route_24h']=any(r[k] and r[k]>=cutoff for k in ('last_direct_ok','last_search_ok'))
    return {'generated_at_utc':stamp,'sources':rows,'successful_route_24h':sum(r['successful_route_24h'] for r in rows),'pending_search':len(pending),'note':'A successful route is not proof that all articles or routes were covered. Partial sources may have a successful route.'}

def _update(db,health,stamp):
    for h in health:
        if h['status'] in ('manual','skipped'):continue
        methods=h.get('direct_methods',[])
        # Legacy manifests use method string. Require actual successful direct route.
        if 'direct_methods' not in h and h['status'] in ('ok','empty','partial'):
            methods=[m for m in h.get('method','').split('+') if m in ('rss','rss_discovered','listing','github_releases','github_merged_pr','news_sitemap')]
        direct=stamp if methods else None
        search=stamp if h.get('search_status') in ('ok','empty') or ('search_status' not in h and h['status'] in ('ok','empty') and 'news' in h.get('method','').split('+')) else None
        db.execute('''INSERT INTO source_coverage VALUES(?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET group_name=excluded.group_name,last_attempt=excluded.last_attempt,last_direct_ok=COALESCE(excluded.last_direct_ok,last_direct_ok),last_search_ok=COALESCE(excluded.last_search_ok,last_search_ok),last_status=excluded.last_status''',(h['source_id'],h['group'],stamp,direct,search,h['status']))

def publish(db, data, target, stamp, resolved, row_dict, organize, write_report, health):
    """Archive target and 5 prior days. Keep late discoveries distinct from target-day count."""
    db.execute('CREATE TABLE IF NOT EXISTS archive_seen(day TEXT, identity TEXT, PRIMARY KEY(day,identity))')
    db.execute('CREATE TABLE IF NOT EXISTS archive_baselines(day TEXT PRIMARY KEY)')
    db.execute('CREATE TABLE IF NOT EXISTS late_candidates(day TEXT, identity TEXT, detected_at TEXT, payload TEXT, PRIMARY KEY(day,identity))')
    target_d=date.fromisoformat(target)
    # Seed older records on first migration: not a claim of new discoveries.
    for n in range(6):
        day=(target_d-timedelta(days=n)).isoformat()
        raw=[row_dict(x) for x in db.execute('SELECT * FROM articles WHERE date_jst=?',(day,))]
        active,_=organize([x for x in raw if x['url'] not in resolved])
        active=[x for x in active if x['triage']!='exclude']
        baseline=db.execute('SELECT 1 FROM archive_baselines WHERE day=?',(day,)).fetchone()
        folder=data/'archive'/day
        folder.mkdir(parents=True,exist_ok=True)
        for g in GROUPS:
            for f in folder.glob(g+'_*.md'):f.unlink()
            write_report(g,day,[x for x in active if x['group']==g],{},folder)
        counts=Counter(x['group'] for x in active)
        dump(folder/'index.json',{'date_jst':day,'generated_at_utc':stamp,'counts':{g:counts[g] for g in GROUPS},'status':'candidate_collection_only'})
        for x in active:
            identity=x['url']
            new=not db.execute('SELECT 1 FROM archive_seen WHERE day=? AND identity=?',(day,identity)).fetchone()
            db.execute('INSERT OR IGNORE INTO archive_seen VALUES(?,?)',(day,identity))
            # Existing historical snapshot + newly appearing URL, not simply a new classification.
            # An initial migration can also identify a genuinely late first observation.
            first=x.get('first_seen_utc')
            observed_late=bool(first and datetime.fromisoformat(first).astimezone(JST).date()>date.fromisoformat(day)+timedelta(days=1))
            if n and new and (baseline or observed_late):
                db.execute('INSERT OR IGNORE INTO late_candidates VALUES(?,?,?,?)',(day,identity,stamp,json.dumps(x,ensure_ascii=False)))
            # Refresh payload to reflect enrichment; retain first discovery time.
            db.execute('UPDATE late_candidates SET payload=? WHERE day=? AND identity=?',(json.dumps(x,ensure_ascii=False),day,identity))
        db.execute('INSERT OR IGNORE INTO archive_baselines VALUES(?)',(day,))
    # Keep a rolling 7-day journal; suppress stale aliases and rows now removed from the dated DB.
    start=(target_d-timedelta(days=7)).isoformat();recovered={g:[] for g in GROUPS}
    for day,identity,detected,payload in db.execute('SELECT * FROM late_candidates WHERE day>=? AND day<? ORDER BY day DESC, detected_at DESC',(start,target)):
        if identity in resolved:continue
        # Read current date rather than resurrect an item corrected to another date.
        if not db.execute('SELECT 1 FROM articles WHERE url=? AND date_jst=?',(identity,day)).fetchone():continue
        x=json.loads(payload);x['recovered_at_utc']=detected
        if x['triage']!='exclude':recovered[x['group']].append(x)
    for g,items in recovered.items():
        dump(data/'latest'/f'{g}_recovery.json',{'group':g,'target_date_jst':target,'status':'late_candidates_not_delivery_log','items':items,'note':'Original dates retained. May recur in successive runs; compare with prior digest if accessible.'})
    db.commit()
    return {g:len(v) for g,v in recovered.items()}
