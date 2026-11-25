"""Construct explicit catalog from the four current ChatGPT news tasks (2026-11-25).
All sources in the catalog are discovery inputs, not proof of a story.
"""
import json
from pathlib import Path

sources=[]

def add(group, label, domain, topics, *, via='news', tier='all', role='specialist', url=None, query=None, locale='en'):
    key=f'{group}-{label}'.lower().replace(' ','-').replace('/','-').replace('.','-')
    obj=dict(id=key, group=group, label=label, topic=topics, kind=via, tier=tier, role=role, domain=domain, homepage=url or 'https://'+domain)
    if query: obj['query']=query
    if via=='rss': obj['feed_url']=url
    if locale!='en':obj['locale']=locale
    sources.append(obj)

def rss(group,label,domain,topic,feed,tier='core',role='specialist'):
    add(group,label,domain,topic,via='rss',tier=tier,role=role,url=feed)

def official(group,label,domain,topic,*,tier='all',query=None):
    add(group,label,domain,topic,tier=tier,role='official',query=query)

def news(group,label,domain,topic,*,tier='all',query=None,locale='en',role='specialist'):
    add(group,label,domain,topic,tier=tier,query=query,locale=locale,role=role)

def git(group,label,repo,topic,*,tier='core',kind='github_releases'):
    add(group,label,'github.com',topic,tier=tier,via=kind,url='https://github.com/'+repo,role='developer')
    sources[-1]['repository']=repo

def manual(group,label,link,topic,note):
    add(group,label,link.split('/')[2],topic,via='manual',tier='manual',role='leak_sensor',url=link)
    sources[-1]['note']=note

# ① MOTORSPORT — original 7:00 task
rss('motorsport','Autosport F1','autosport.com','F1','https://www.autosport.com/rss/f1/news/')
rss('motorsport','Autosport all','autosport.com','other_motorsport','https://www.autosport.com/rss/all/news/',tier='all')
rss('motorsport','The Race','the-race.com','F1','https://www.the-race.com/feed/')
rss('motorsport','DirtFish','dirtfish.com','WRC','https://dirtfish.com/feed/')
for label,domain,topic in [
 ('Formula 1 Official','formula1.com','F1'),('FIA','fia.com','F1'),
 ('Motorsport EN F1','motorsport.com','F1'),('Motorsport JP','jp.motorsport.com','F1'),
 ('AMuS','auto-motor-und-sport.de','F1'),('AutoRacer','autoracer.it','F1'),
 ('RaceFans','racefans.net','F1'),('Sky Sports F1','skysports.com','F1'),
 ('GPblog','gpblog.com','F1'),('RacingNews365','racingnews365.com','F1'),
 ('PlanetF1','planetf1.com','F1'),('F1Technical','f1technical.net','F1'),
 ('FormulaPassion','formulapassion.it','F1'),('AUTOSPORT web','as-web.jp','other_motorsport'),
 ('WRC Official','wrc.com','WRC'),('Rallit','rallit.fi','WRC'),
 ('RallyJournal','rallyjournal.com','WRC'),('WRCWings','wrcwings.tech','WRC'),
 ('RALLY PLUS','rallyplus.net','WRC'),('eWRC results','ewrc-results.com','WRC'),
 ('FIA WEC','fiawec.com','WEC'),('Sportscar365','sportscar365.com','WEC'),
 ('DailySportscar','dailysportscar.com','WEC'),
 ('Super GT Official','supergt.net','Super GT'),('Super Formula Official','superformula.net','Super Formula'),
 ('IndyCar Official','indycar.com','IndyCar'),('RACER','racer.com','IndyCar'),
 ('NASCAR Official','nascar.com','NASCAR'),('Dakar Official','dakar.com','Dakar')]:
    official('motorsport',label,domain,topic,tier='core') if 'Official' in label or label=='FIA' else news('motorsport',label,domain,topic,tier='core' if label in ('Motorsport EN F1','AMuS','AutoRacer','RaceFans','Rallit','RallyJournal','WRCWings','Sportscar365','RACER') else 'all')

# ② PC AI SMARTPHONE — original 7:15 task
for label,domain,topic,kind in [
 ('AMD','amd.com','pc','official'),('NVIDIA','nvidia.com','pc','official'),
 ('Intel','intel.com','pc','official'),('Microsoft Windows','microsoft.com','pc','official'),
 ('Samsung Semiconductor','semiconductor.samsung.com','pc','official'),
 ('Micron','micron.com','pc','official'),('SK hynix','news.skhynix.com','pc','official'),
 ('TSMC','tsmc.com','pc','official'),('JEDEC','jedec.org','pc','official'),
 ('TechPowerUp','techpowerup.com','pc','news'),('Tom’s Hardware','tomshardware.com','pc','news'),
 ('ComputerBase','computerbase.de','pc','news'),('PC Watch','pc.watch.impress.co.jp','pc','news'),
 ('AKIBA PC Hotline','akiba-pc.watch.impress.co.jp','pc','news'),('TrendForce','trendforce.com','pc','news'),
 ('Igor’sLAB','igorslab.de','pc','news'),('TFTCentral','tftcentral.co.uk','pc','news'),
 ('VideoCardz','videocardz.com','pc','news'),('BenchLife','benchlife.info','pc','news'),
 ('Wccftech','wccftech.com','pc','news'),('Hardware Busters','hwbusters.com','pc','news'),
 ('StorageReview','storagereview.com','pc','news'),('RTINGS Monitor','rtings.com','pc','news'),
 ('Gamers Nexus','gamersnexus.net','pc','news'),('NichePCGamer','nichepcgamer.com','pc','news'),
 ('OpenAI','openai.com','ai','official'),('OpenAI Help','help.openai.com','ai','official'),
 ('Anthropic','anthropic.com','ai','official'),('Claude Help','support.claude.com','ai','official'),
 ('Google AI','blog.google','ai','official'),('Google DeepMind','deepmind.google','ai','official'),
 ('Artificial Analysis','artificialanalysis.ai','ai','news'),('Ars Technica','arstechnica.com','ai','news'),
 ('The Verge','theverge.com','ai','news'),('TechCrunch','techcrunch.com','ai','news'),
 ('Reuters AI','reuters.com','ai','news'),('TestingCatalog','testingcatalog.com','ai','news'),
 ('HelenTech','helentech.jp','ai','news'),('GSMArena','gsmarena.com','smartphones','news'),
 ('Notebookcheck mobile','notebookcheck.net','smartphones','news'),
 ('ITmedia Mobile','itmedia.co.jp','smartphones','news')]:
    (official if kind=='official' else news)('pc_ai',label,domain,topic,tier='core' if label in ('TechPowerUp','Tom’s Hardware','ComputerBase','PC Watch','TrendForce','Igor’sLAB','TFTCentral','VideoCardz','OpenAI','OpenAI Help','Anthropic','Google AI','Artificial Analysis','TestingCatalog','GSMArena') else 'all')
rss('pc_ai','9to5Google','9to5google.com','ai','https://9to5google.com/feed/')
rss('pc_ai','9to5Mac','9to5mac.com','ai','https://9to5mac.com/feed/',tier='all')
manual('pc_ai','Tibor Blaho','https://x.com/btibor91','ai','Public Web/App feature flags; account content may require authentication')
manual('pc_ai','AssembleDebug','https://www.androidauthority.com/author/AssembleDebug/','ai','APK reverse engineering; verify original author and publication time')
manual('pc_ai','Board Channels','https://www.chiphell.com/','pc','China industry forum; manual sourcing and validation required')

# ③ GAMES/HANDHELDS — original 7:30 task
rss('games_handhelds','Retro Handhelds','retrohandhelds.gg','handhelds','https://retrohandhelds.gg/feed/')
for label,domain,topic in [
 ('Android Authority Handheld','androidauthority.com','handhelds'),
 ('Notebookcheck Handheld','notebookcheck.net','handhelds'),
 ('Retro Game Corps','retrogamecorps.com','handhelds'),
 ('Retro Dodo','retrododo.com','handhelds'),
 ('Joey Retro Handhelds','joeysretrohandhelds.com','handhelds'),
 ('Retroid','goretroid.com','handhelds'),('AYN','ayn.hk','handhelds'),
 ('AYANEO','ayaneo.com','handhelds'),('ANBERNIC','anbernic.com','handhelds'),
 ('GPD','gpd.hk','handhelds'),('OneXPlayer','onexplayerstore.com','handhelds'),
 ('Powkiddy','powkiddy.com','handhelds'),('TrimUI','trimui.com','handhelds'),
 ('Valve Steam Deck','store.steampowered.com','handhelds'),
 ('GTPlanet','gtplanet.net','racing_games'),('Traxion','traxion.gg','racing_games'),
 ('OverTake','overtake.gg','racing_games'),('PCGamingWiki','pcgamingwiki.com','racing_games'),
 ('RaceDepartment Archives','racedepartment.com','racing_games'),('Steam racing updates','store.steampowered.com','racing_games'),
 ('Azur Lane JP','azurlane.jp','azur_lane'),('Yostar JP','yostar.co.jp','azur_lane')
]:
    role='official' if label in ('Retroid','AYN','AYANEO','ANBERNIC','GPD','Powkiddy','Valve Steam Deck','Azur Lane JP','Yostar JP') else 'specialist'
    add('games_handhelds',label,domain,topic,role=role,tier='core' if label in ('Android Authority Handheld','Notebookcheck Handheld','Retro Dodo','Retroid','AYN','AYANEO','ANBERNIC','GTPlanet','Traxion','OverTake','Azur Lane JP') else 'all')
for label,repo,topic in [
 ('RPCS3','RPCS3/rpcs3','emulators'),('Xenia Canary','xenia-canary/xenia-canary','emulators'),
 ('xemu','xemu-project/xemu','emulators'),('Dolphin','dolphin-emu/dolphin','emulators'),
 ('Cemu','cemu-project/Cemu','emulators'),('Azahar','azahar-emu/azahar','emulators'),
 ('Eden mirror','eden-emulator/mirror','emulators'),
 ('ROCKNIX','ROCKNIX/distribution','handhelds'),('ROCKNIX nightly','ROCKNIX/distribution-nightly','handhelds'),
 ('GammaOS Next','TheGammaSqueeze/GammaOSNext','handhelds'),
 ('KNULLI','knulli-cfw/knulli-linux','handhelds'),('Batocera','batocera-linux/batocera.linux','handhelds'),
 ('FEX','FEX-Emu/FEX','handhelds'),('Proton','ValveSoftware/Proton','handhelds')]:
    git('games_handhelds',label,repo,topic)
for label,repo,topic in [
 ('ROCKNIX merged PR','ROCKNIX/distribution','handhelds'),
 ('RPCS3 merged PR','RPCS3/rpcs3','emulators'),
 ('Dolphin merged PR','dolphin-emu/dolphin','emulators'),
 ('GammaOS merged PR','TheGammaSqueeze/GammaOSNext','handhelds')]:
    git('games_handhelds',label,repo,topic,tier='all',kind='github_merged_pr')
manual('games_handhelds','RetroHandhelds Discord','https://retrohandhelds.gg/','handhelds','Discord and QQ references require manual source validation')
manual('games_handhelds','r SBCGaming','https://www.reddit.com/r/SBCGaming/','handhelds','User posts are unverified until original material is located')
manual('games_handhelds','RetroDeadFred','https://www.youtube.com/','handhelds','Locate original creator post from specialist coverage; channel URL not presumed')
manual('games_handhelds','TeknoParrot','https://teknoparrot.com/','racing_games','Racing titles only; proprietary feeds not assumed')

# ④ AUDIO — original 7:45 task
rss('audio','Headfonics','headfonics.com','wired','https://headfonics.com/feed/')
rss('audio','Headfonia','headfonia.com','portable_dac','https://www.headfonia.com/feed/',tier='all')
for label,domain,topic,role in [
 ('AV Watch Audio','av.watch.impress.co.jp','wired','specialist'),
 ('PHILE WEB','phileweb.com','wired','specialist'),
 ('e earphone','e-earphone.blog','wired','retailer'),
 ('Head-Fi','head-fi.org','wired','community'),
 ('CanJam','canjamglobal.com','wired','official'),
 ('Linsoul','linsoul.com','wired','retailer'),
 ('HiFiGo','hifigo.com','wired','retailer'),
 ('SHENZHENAUDIO','shenzhenaudio.com','wired','retailer'),
 ('MusicTeck','musicteck.com','wired','retailer'),
 ('xMEMS','xmems.com','wired','official'),
 ('DUNU','dunu-topsound.com','wired','official'),
 ('Moondrop','moondroplab.com','wired','official'),
 ('FiiO','fiio.com','portable_dac','official'),
 ('iBasso','ibasso.com','portable_dac','official'),
 ('Shanling','en.shanling.com','portable_dac','official'),
 ('Questyle','questyle.com','portable_dac','official'),
 ('Qudelix','qudelix.com','bluetooth_dac','official'),
 ('Audio Science Review','audiosciencereview.com','portable_dac','specialist'),
 ('L7AudioLab','l7audiolab.com','portable_dac','specialist'),
 ('SoundGuys','soundguys.com','tws','specialist'),
 ('RTINGS Headphones','rtings.com','tws','specialist'),
 ('Scarbir','scarbir.com','tws','specialist'),
 ('Sony Audio','sony.com','tws','official'),
 ('Apple AirPods','apple.com','tws','official'),
 ('Samsung Audio','samsung.com','tws','official'),
 ('Bose','bose.com','tws','official'),
 ('Sennheiser','sennheiser-hearing.com','tws','official'),
 ('Technics','technics.com','tws','official'),
 ('JBL','jbl.com','tws','official'),
 ('Nothing','nothing.tech','tws','official'),
 ('OnePlus Audio','oneplus.com','tws','official'),
 ('EarFun','myearfun.com','tws','official'),
 ('AVIOT','aviot.jp','tws','official'),
 ('Bluetooth SIG','bluetooth.com','tws','official'),
 ('Qualcomm Audio','qualcomm.com','tws','official'),
 ('The Walkman Blog','thewalkmanblog.blogspot.com','tws','leak_sensor'),
 ('SamMobile','sammobile.com','tws','leak_sensor'),
 ('MacRumors','macrumors.com','tws','leak_sensor'),
 ('Android Authority TWS','androidauthority.com','tws','specialist')]:
    add('audio',label,domain,topic,role=role,tier='core' if label in ('AV Watch Audio','PHILE WEB','e earphone','Head-Fi','Linsoul','HiFiGo','FiiO','iBasso','Qudelix','SoundGuys','RTINGS Headphones','Sony Audio','Qualcomm Audio','The Walkman Blog') else 'all')
rss('audio','9to5Mac AirPods','9to5mac.com','tws','https://9to5mac.com/feed/',tier='all')
manual('audio','TWS FCC records','https://www.fcc.gov/oet/ea/fccid','tws','Regulatory search is not scraped by default; needs model number search')
manual('audio','Manufacturer Weibo','https://weibo.com/','wired','Chinese SNS may require login; not automated')


# Direct feeds detected by public endpoints; verification at execution time is still required.
# RDF 1.0 and RSS 2.0 are both supported by collector.py.
upgrade_feeds={
    ('pc_ai','Tom’s Hardware'):'https://www.tomshardware.com/feeds/all',
    ('pc_ai','ComputerBase'):'https://www.computerbase.de/rss/news.xml',
    ('pc_ai','PC Watch'):'https://pc.watch.impress.co.jp/data/rss/1.0/pcw/feed.rdf',
    ('audio','AV Watch Audio'):'https://av.watch.impress.co.jp/data/rss/1.0/avw/feed.rdf',
    ('audio','MacRumors'):'https://www.macrumors.com/macrumors.xml',
    ('games_handhelds','GTPlanet'):'https://www.gtplanet.net/feed/',
}
for s in sources:
    feed=upgrade_feeds.get((s['group'],s['label']))
    if feed:
        s['kind']='rss'
        s['feed_url']=feed
        s['tier']='core'
# Filter highly general feeds when used for a narrower user topic.
source_filters={
    ('pc_ai','9to5Google'):['Gemini','AI Mode','AI Overview','NotebookLM','Antigravity','Google AI','DeepMind'],
    ('pc_ai','9to5Mac'):['AI','Gemini','ChatGPT','Claude'],
    ('audio','9to5Mac AirPods'):['AirPods','Beats','earbud','headphone','Bluetooth audio'],
    ('audio','MacRumors'):['AirPods','Beats','earbud','headphone','audio'],
    ('audio','AV Watch Audio'):['イヤホン','ヘッドホン','DAC','オーディオ','Bluetooth','ノイキャン','TWS','ヘッドセット','コーデック'],
}
for s in sources:
    filters=source_filters.get((s['group'],s['label']))
    if filters:s['include_any']=filters

# Correct metadata: an RSS feed URL is not the site's homepage.
for s in sources:
    if s['kind']=='rss': s['homepage']='https://'+s['domain']

ids=[s['id'] for s in sources]
if len(ids)!=len(set(ids)):
    from collections import Counter
    raise ValueError('Duplicate IDs '+str([k for k,v in Counter(ids).items() if v>1]))

Path('sources.json').write_text(json.dumps({'schema_version':1,'sources':sources},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Catalog:',len(sources),'sources; automation candidates',sum(s['kind']!='manual' for s in sources),'manual',sum(s['kind']=='manual' for s in sources))
for g in ('motorsport','pc_ai','games_handhelds','audio'):
    sg=[s for s in sources if s['group']==g]
    print(g,len(sg),'active',sum(s['kind']!='manual' for s in sg))
