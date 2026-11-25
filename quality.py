"""Conservative candidate triage: not a fact checker. Keep rejected rows in audit/DB."""
import re, json, hashlib
from collections import defaultdict
from urllib.parse import urlparse, urljoin
from datetime import datetime
from bs4 import BeautifulSoup

AUDIO=r'\b(?:iem|iems|earbuds?|earphones?|headphones?|headset|airpods|galaxy buds|pixel buds|tws|anc|auracast|le audio|aptx|dac|dongle|headphone amp|btr\d+|heddphone)\b|イヤホン|ヘッドホン|ヘッドフォン|ノイキャン|ポータブルDAC|耳機|耳机|解码耳放'
PHONE=r'\b(?:smartphones?|foldables?|galaxy (?:s\d+|z fold|z flip)|iphone|mate x\d+|pixel \d+|oneplus \d+|coloros|one ui|android update)\b|スマートフォン|スマホ|折りたたみスマホ'
AI=r'\b(?:chatgpt|openai|anthropic|claude|gemini|deepmind|notebooklm|grok|copilot|llm|ai agent|codex|artificial analysis|generative ai)\b|生成AI|人工知能'
HAND=r'\b(?:handheld|retroid|anbernic|ayn|ayaneo|konkr|rocknix|gammaos|portareos|dslot|knulli|batocera|steam deck|legion go|rog ally|powkiddy|trimui|onexplayer|gpd win|mangmi|magicx)\b|携帯ゲーム機|ハンドヘルド'
RACING=r'\b(?:gran turismo|forza|iracing|assetto corsa|racing game|sim racing|simracing|rally game|le mans ultimate|automobilista|race room|raceroom|need for speed|wrc generations|f1 \d{2,4}|dirt rally|galactic racer)\b|レースゲーム|ハンコン'
PERIPH=r'\b(?:fanatec|moza|simagic|simucube|thrustmaster|pedals?|wheelbase|force feedback|gamepad|controller|shifter|stream deck|capture card)\b|ハンコン|ペダル|コントローラー'
PC=r'\b(?:gpu|cpu|geforce|radeon|ryzen|intel|nvidia|ssd|dram|nand|ddr[456]|hbm|oled|monitor|display|windows|bios|driver|pc|motherboard|chipset|processor|semiconductor|12vhpwr|12v-2x6|power supply|hwinfo)\b|半導体|モニター|メモリ|グラフィックス|マザーボード'
SALE=r'black friday|cyber monday|\b(?:coupon|discount|deals?|save \$|\d+% off|\$\d+ off|\d+ off on amazon|hit a new low|drop[s]? to \$|lowest price|giveaway|price drop|sold:|like new)\b|ブラックフライデー|セール|クーポン|特価|中古'
NEW=r'\b(?:launch\w*|releas\w*|announc\w*|unveil\w*|pre[- ]?order|shipping|available|firmware|updat\w*|review|introduc\w*|first impressions|new|fix\w*|improv\w*)\b|発表|発売|予約|更新|レビュー|出荷|新品|发布|预售|上市|Vorstellung|vorgestellt'
NAV=r'^(?:[-–—\s]*[\w. ]{0,70})$'

def has(pattern,text): return bool(re.search(pattern,text,re.I))
def clean_title(x):
    t=x.get('title','').strip(); pub=x.get('publisher','').strip()
    if pub and t.casefold().endswith((' - '+pub).casefold()):t=t[:-(len(pub)+3)]
    return t.strip()
def title_key(x): return re.sub(r'[^\w]+',' ',clean_title(x).casefold()).strip()

def triage(x):
    t=clean_title(x); d=x.get('description',''); text=t+' '+d; group=x.get('group') or x.get('group_name'); topic=x.get('topic',''); p=urlparse(x.get('url','')).path.lower()
    def out(g,tp,state,why):return dict(group=g,topic=tp,triage=state,triage_reason=why)
    if not t.strip(' -–—') or t.startswith('- ') or has(r'^(?:news|latest articles|member login|power rankings archives|oneplus community|about us|home|careers|over-ear headphone|wireless over-ear noise cancelling headphones)(?:\s*[-|].*)?$',t):return out(group,topic,'exclude','一覧・ナビゲーション候補')
    if has(r'/(?:author|category|tag|careers|login|account)/[^/]+/?$',p) and not x.get('timestamp_basis','').startswith('github_'):return out(group,topic,'exclude','一覧・プロフィール候補')
    if has(r'\b(?:apply now|job opening|job vacancy|careers at|hiring now|senior .* engineer in|sr\. .* engineer in|engineer lead .* in|software development .* in)\b|採用情報|求人',t):return out(group,topic,'exclude','求人・採用ページ')
    if has(SALE,t) and not has(r'launch date|launches|pre[- ]?order|new product|発売日|予約開始',t):return out(group,topic,'exclude','通常セール・販促・中古')
    if group=='audio' and has(r'\b(?:desktop|stationary|benchtop)\b.{0,40}\b(?:amp|dac|amplifier)\b|据え置き|\b(?:dap|digital audio player|ddc|digital audio interface)\b',text) and not has(r'portable|dongle|ポータブル',t):return out(group,topic,'exclude','据え置き/DAP/DDC候補')
    if group=='audio' and has(r'\b(?:sold|wanted):|auracast location profile|market blueprint|member login',t):return out(group,topic,'exclude','中古・施設一覧・一般資料')
    if group=='audio' and has(r'\b(?:smart tv|tv launcher|subwoofer|party speaker|desktop headphone amp)\b',t):return out(group,topic,'exclude','対象外機器')
    if group=='audio' and has(AUDIO,t):
        if has(r'\b(?:colorway|new color|product\s*\(red\)|\(red\) products)\b|色違い',text) and not has(r'firmware|driver technology|新機能',t):return out(group,topic,'exclude','色違い中心')
        tp='bluetooth_dac' if has(r'\bbtr\d+|bluetooth.{0,35}\bdac|bluetooth receiver',text) else 'portable_dac' if has(r'\bdac\b|dongle|ポータブルDAC',t) else 'tws' if has(r'earbuds|airpods|buds|tws|auracast|le audio|aptx|wireless|bluetooth|ノイキャン',t) else 'wired'
        return out('audio',tp,'priority' if has(NEW,text) else 'review','対象オーディオ候補')
    if group!='motorsport' and has(AUDIO,t) and not has(r'\b(?:ai model|chatgpt|claude|gpu driver)\b',t):return out('audio','tws' if has(r'buds|airpods|wireless|bluetooth|tws',t) else 'portable_dac' if has(r'\bdac\b|dongle',t) else 'wired','review','オーディオへ再分類')
    if group!='motorsport' and has(HAND,t) and not x.get('timestamp_basis','').startswith('github_'):return out('games_handhelds','handhelds','priority' if has(NEW,text) else 'review','ハンドヘルド候補')
    if group!='motorsport' and has(RACING,t):
        if has(r'\be[- ]?sports\b|world finals|daily races|rankings|rating',t) and not has(r'update|patch|physics|server shutdown',t):return out('games_handhelds','racing_games','exclude','競技・ランキング')
        return out('games_handhelds','peripherals' if has(PERIPH,t) else 'racing_games','priority' if has(NEW,text) else 'review','レースゲーム候補')
    if group=='games_handhelds' and has(PERIPH,t):return out(group,'peripherals','priority' if has(NEW,text) else 'review','周辺機器候補')
    if group!='motorsport' and has(PHONE,t) and not has(AI,t):return out('pc_ai','smartphones','priority' if has(NEW,text) else 'review','スマートフォンへ分類')
    if group!='motorsport' and has(AI,t):return out('pc_ai','ai','priority' if has(NEW,text) else 'review','AI候補')
    if group=='motorsport':
        if has(r'motogp|world superbike|\bfootball\b|soccer|premier league|midfielder|\bnfl\b|\bnba\b',t):return out(group,topic,'exclude','対象外競技')
        if has(r'sim racing|simracing|esports|e-sports',t):return out(group,topic,'exclude','競技ゲーム')
        for pattern,tp in [(r'\bwrc\b|rally1|rally2|world rally|ラリー','WRC'),(r'\bwec\b|hypercar|le mans|ハイパーカー','WEC'),(r'super formula|スーパーフォーミュラ','Super Formula'),(r'super gt|スーパーgt','Super GT'),(r'indycar|indy 500|インディカー','IndyCar'),(r'nascar','NASCAR'),(r'dakar|ダカール','Dakar'),(r'\bf1\b|formula 1|ferrari|hamilton|verstappen|grand prix|角田|ラスベガスgp','F1')]:
            if has(pattern,t):return out(group,tp,'priority' if has(r'withdraw|exit|signs?|contract|transfer|join|leaves?|retire|regulation|rule change|launch|announce|confirmed|technical|upgrade|engine|crash|penalty|wins?|champion|results?|撤退|契約|移籍|発表|規則|優勝|結果|開発',text) else 'review','競技名一致・新規性の確認')
        return out(group,topic,'review','競技・記事内容の確認待ち')
    if group=='games_handhelds' and x.get('timestamp_basis','').startswith('github_'):
        if has(r'update kernel configs/device documentation|fix build|update qt|remove git_shallow|canary_experimental',t):return out(group,topic,'review','開発ビルド・軽微変更の内容確認')
        return out(group,topic,'priority' if x.get('timestamp_basis')=='github_release_published' and not has(r'nightly|canary_experimental',t) or has(r'fix|improve|release|charging|azahar|proton|vulkan|save',text) else 'review','GitHub開発情報')
    if group=='games_handhelds' and has(r'azur lane|アズールレーン',text):return out(group,'azur_lane','priority','ゲーム本編確認')
    if group=='games_handhelds' and has(r' - Steam$',t) and not has(NEW,text):return out(group,topic,'exclude','ストアの既存商品候補')
    if group=='pc_ai' and has(PC,t):return out(group,'pc','priority' if has(NEW,text) else 'review','PC技術候補')
    if group=='audio' and has(r'galaxy watch|wear os|smart tv|\btvs?\b|speaker|subwoofer|macbook|spotify|keyboard|kindle|google photos|apple wallet|apple pay|fire tv|galaxy fit|fitbit|google maps|android auto|stylus|google translate|samsung browser|app lock|android storage|google tv|スマートテレビ|車載',t):return out(group,topic,'exclude','対象外機器・サービス')
    return out(group,topic,'review','関連性・新規性要確認')

def page_metadata(html, url):
    soup=BeautifulSoup(html,'html.parser'); meta={}
    def content(*names):
        for n in names:
            el=soup.find('meta',attrs={'property':n}) or soup.find('meta',attrs={'name':n}) or soup.find('meta',attrs={'itemprop':n})
            if el and el.get('content'):return el['content']
        return ''
    def walk(o):
        if isinstance(o,list):
            for i in o:yield from walk(i)
        elif isinstance(o,dict):
            yield o
            if '@graph' in o:yield from walk(o['@graph'])
    for script in soup.find_all('script',type='application/ld+json'):
        try: nodes=list(walk(json.loads(script.string or script.get_text())))
        except (ValueError,TypeError):continue
        for n in nodes:
            typ=n.get('@type',[]); typ=[typ] if isinstance(typ,str) else typ or []
            if not any(str(v).endswith(('Article','BlogPosting','NewsArticle','Report','Review')) for v in typ):continue
            for k in ('datePublished','dateModified','headline','description'):
                if n.get(k) and not meta.get(k):meta[k]=str(n[k])
    for k,names in {'datePublished':('article:published_time','datePublished','pubdate'),'dateModified':('article:modified_time','dateModified'),'headline':('og:title',),'description':('description','og:description')}.items():
        if not meta.get(k):meta[k]=content(*names)
    can=soup.find('link',rel='canonical'); meta['canonical']=urljoin(url,can.get('href','')) if can and can.get('href') else url
    meta['description']=re.sub(r'\s+',' ',BeautifulSoup(meta.get('description',''),'html.parser').get_text(' ',strip=True))[:350]
    return meta

def organize(rows):
    """Exact URL merge across groups + conservative same-title event suggestions. Never delete audit rows."""
    by_url={}; raw=[]
    for x in rows:
        x=dict(x); x.update(triage(x)); raw.append(x)
        key=(x['url'],x['id']) if x.get('timestamp_basis')=='page_change_observed' else x['url']; old=by_url.get(key)
        evidence={k:x.get(k) for k in ('url','source','publisher','timestamp_basis','published_utc','title')}
        if not old:
            x['sources']=[evidence];by_url[key]=x;continue
        rank=lambda y: (y['triage']=='priority',y['triage']!='exclude',y.get('link_role')!='discovery_link',len(y.get('description','')))
        evidence_list=old['sources']+[evidence]
        if rank(x)>rank(old):by_url[key]=x;old=x
        old['sources']=evidence_list
    active=list(by_url.values()); clusters=defaultdict(list)
    # Same normalized title: suggestions only; not proof of independent corroboration.
    for x in active:
        key=title_key(x)
        if len(key)>=25 and x['triage']!='exclude':clusters[(x['group'],x['topic'],key)].append(x)
    for k,items in clusters.items():
        if len(items)>1:
            cid=hashlib.sha256(str(k).encode()).hexdigest()[:12]
            for x in items:x['possible_event_id']=cid
    # Conservative explicit product + milestone groups; only hints, keep all independent evidence.
    product_patterns=[r'\bheddphone\s+dx\b',r'\bnothing.{0,24}\bear\s*\(?note\)?',r'\bclaude\s+ship\b',r'\b(?:earfun\s+)?air\s+pro\s+5\b',r'\bfiio\s+btr\s*25\b']
    events=defaultdict(list)
    for x in active:
        if x['triage']=='exclude':continue
        t=clean_title(x).casefold()
        stage='review' if has(r'review|first impressions|測定|レビュー',t) else 'shipping' if has(r'shipping|出荷',t) else 'preorder' if has(r'pre[- ]?order|予約',t) else 'sale' if has(r'on sale|now available|販売開始|発売開始',t) else 'announcement' if has(r'announc|unveil|introduc|upcoming|launch date|発表|公開',t) else None
        if not stage:continue
        for n,pat in enumerate(product_patterns):
            if has(pat,t):events[(x['group'],n,stage)].append(x)
    for k,items in events.items():
        if len(items)>1:
            cid=hashlib.sha256(str(k).encode()).hexdigest()[:12]
            for x in items:x['possible_event_id']=cid
    return active,raw
