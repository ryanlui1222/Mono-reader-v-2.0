"""Monoreader connection milestone. Authenticated reading, editing and metadata lookup service."""
import json
from contextvars import ContextVar
from collections import OrderedDict
import base64
import re
import uuid
from datetime import datetime, timezone
import hashlib
import hmac
import os
import time
from collections import deque
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, quote

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
# One HTTP connection pool per incoming request, shared by its SQL calls.
_request_client = ContextVar('request_client', default=None)
_refresh_metadata = ContextVar('refresh_metadata', default=False)
_metadata_cache = OrderedDict()
_metadata_epoch = 0

@app.middleware('http')
async def database_connection_scope(request, call_next):
    global _metadata_epoch
    writing = request.method in ('POST','PUT','PATCH','DELETE')
    if writing:
        _metadata_epoch += 1
        _metadata_cache.clear()
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
        token = _request_client.set(client)
        refresh = _refresh_metadata.set(request.query_params.get('refresh') == '1')
        try:
            response = await call_next(request)
            response.headers['Server-Timing'] = f'app;dur={(time.perf_counter()-started)*1000:.1f}'
            return response
        finally:
            if writing:
                _metadata_epoch += 1
                _metadata_cache.clear()
            _request_client.reset(token)
            _refresh_metadata.reset(refresh)

async def cached_metadata(sql, args=None):
    # Never cache private data outside this process; auth is checked by routes.
    key = (os.getenv('TURSO_DATABASE_URL',''), os.getenv('TURSO_AUTH_TOKEN',''),
           sql, tuple(args or []))
    now = time.monotonic()
    item = _metadata_cache.get(key)
    if item and now-item[0] < 60 and not _refresh_metadata.get():
        _metadata_cache.move_to_end(key)
        return item[1]
    epoch = _metadata_epoch
    result = await query(sql, args)
    if epoch == _metadata_epoch:
        _metadata_cache[key] = (time.monotonic(), result)
        _metadata_cache.move_to_end(key)
        while len(_metadata_cache)>256:
            _metadata_cache.popitem(last=False)
    return result

ROOT = Path(__file__).parent
COOKIE = '__Host-monoreader'
TABLES = {
    'articles': ['SortDate'], 'academic_pubs': ['added_date', 'publish_date'],
    'media_vault': ['sort_date'], 'omni_vault': ['added_date'],
    'custom_resources': ['added_date'], 'bibliography_notes': ['added_date'],
}
# Best-effort per-instance throttle only: serverless instances do not share memory.
# Use a strong password; a shared limiter is needed before wider public use.
failures = deque(maxlen=100)


def config():
    password = os.getenv('APP_PASSWORD', '')
    secret = os.getenv('SESSION_SECRET', '')
    if len(password) < 12 or len(secret) < 32:
        raise HTTPException(503, '請設定 APP_PASSWORD（至少12字元）與 SESSION_SECRET（至少32字元）。')
    return password, secret


def signature(value):
    password, secret = config()
    return hmac.new(secret.encode(), (value + ':' + password).encode(), hashlib.sha256).hexdigest()


def authenticated(request):
    config()
    token = request.cookies.get(COOKIE, '')
    try:
        expires, sig = token.split('.')
        return int(expires) > time.time() and hmac.compare_digest(sig, signature(expires))
    except (ValueError, TypeError):
        return False


def require_login(request):
    if not authenticated(request):
        raise HTTPException(401, '登入已過期，請重新登入。')


@app.middleware('http')
async def headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Monoreader-Version'] = 'editing-pwa-v9'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    # Native HTML form POSTs can send Origin: null under no-referrer.
    # Preserve the origin for our login/logout CSRF checks.
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


LOGIN = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Monoreader 登入</title><meta name="theme-color" content="#f5f3ed"><link rel="manifest" href="/manifest.webmanifest"><link rel="icon" href="/icon-192.png"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Monoreader"><style>body{background:#f5f3ed;color:#233e38;font:16px/1.7 system-ui;display:grid;place-items:center;min-height:90vh;margin:20px}main{max-width:380px;width:100%}h1{font-family:Georgia,serif;font-size:40px}input,button{box-sizing:border-box;width:100%;padding:14px;font:inherit;margin:10px 0;border:1px solid #c5cec1;border-radius:8px}button{background:#233e38;color:white}p{color:#657268;font-size:14px}</style><main><h1>monoreader</h1><p>私人閱讀與收藏 · 安全登入</p><form method="post" action="/login"><label for="password">你設定的 App 登入密碼</label><input id="password" type="password" name="password" required autocomplete="current-password" maxlength="512"><button>登入</button></form><p>密碼是在 Vercel 的 APP_PASSWORD 設定，不是 GitHub 或 Turso 密碼。</p></main><script>try{for(const k of Object.keys(localStorage)){if(k.startsWith('monoreader-pages-'))localStorage.removeItem(k)}}catch(e){}</script><script src="/pwa.js" defer></script></html>'''


@app.get('/health')
def health():
    return {'status': 'running', 'mode': 'write-enabled' if writes_enabled() else 'read-only', 'version': 'editing-pwa-v9'}


@app.get('/login', response_class=HTMLResponse)
def login_page():
    config()
    return LOGIN


def check_origin(request):
    origin = request.headers.get('origin')
    if not origin:
        return
    # The external HTTPS hostname can differ from the Host seen behind Vercel.
    # Trust only exact configured origins, never arbitrary forwarded headers or
    # a wildcard such as *.vercel.app (which includes other people's projects).
    allowed = {'https://' + request.headers.get('host', '').lower()}
    for name in ('VERCEL_URL', 'VERCEL_BRANCH_URL', 'VERCEL_PROJECT_PRODUCTION_URL'):
        host = os.getenv(name, '').strip().lower()
        if host and '/' not in host and '@' not in host:
            allowed.add('https://' + host)
    allowed.update(x.strip().rstrip('/').lower()
                   for x in os.getenv('APP_ALLOWED_ORIGINS', '').split(',') if x.strip())
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.netloc or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment
            or origin.lower() not in allowed):
        raise HTTPException(403, '來源不符。')


@app.post('/login')
async def login(request: Request):
    check_origin(request)
    password, _ = config()
    now = time.time()
    while failures and failures[0] < now - 300:
        failures.popleft()
    if len(failures) >= 10:
        raise HTTPException(429, '嘗試過多，請五分鐘後再試。')
    body = await request.body()
    if len(body) > 4096:
        raise HTTPException(413, '輸入過長。')
    supplied = parse_qs(body.decode('utf-8', errors='replace')).get('password', [''])[0]
    if not hmac.compare_digest(hashlib.sha256(supplied.encode()).digest(), hashlib.sha256(password.encode()).digest()):
        failures.append(now)
        return HTMLResponse(LOGIN.replace('<form', '<p>密碼不正確，請再試一次。</p><form'), status_code=401)
    expiry = str(int(now + 43200))
    response = RedirectResponse('/', status_code=303)
    response.set_cookie(COOKIE, expiry + '.' + signature(expiry), secure=True, httponly=True, samesite='strict', max_age=43200, path='/')
    return response


@app.post('/logout')
def logout(request: Request):
    check_origin(request)
    response = RedirectResponse('/login', status_code=303)
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='strict', path='/')
    return response


@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    if not authenticated(request):
        return RedirectResponse('/login', status_code=303)
    expires = int(request.cookies[COOKIE].split('.')[0])
    boot = {'expires': expires, 'writes': writes_enabled(), 'cacheKey': signature('cache-v6:' + os.getenv('TURSO_DATABASE_URL', ''))[:32]}
    return (ROOT / 'index.html').read_text(encoding='utf-8').replace('<!--APP_BOOT-->', '<script>window.MONOREADER_BOOT=' + json.dumps(boot) + ';</script>')


def endpoint():
    raw = os.getenv('TURSO_DATABASE_URL', '').strip().replace('libsql://', 'https://', 1)
    token = os.getenv('TURSO_AUTH_TOKEN', '').strip()
    parsed = urlsplit(raw)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment or parsed.path not in ('', '/') or not token:
        raise HTTPException(503, 'Turso 設定缺漏或網址格式不符；請使用原 App 的資料庫 URL 與 Token。')
    return raw.rstrip('/') + '/v2/pipeline', token


def decode_result(payload):
    result = payload['results'][0]
    if result.get('type') != 'ok':
        raise HTTPException(502, '資料庫查詢失敗。請確認 Token 權限與資料表結構。')
    result = result['response']['result']
    columns = [c['name'] for c in result['cols']]
    rows = []
    for row in result['rows']:
        def value(cell):
            if cell['type'] == 'null':
                return None
            if cell['type'] == 'integer':
                return int(cell['value'])
            if cell['type'] == 'float':
                return float(cell['value'])
            return cell.get('value')
        rows.append(dict(zip(columns, map(value, row))))
    return columns, rows


async def query(sql, args=None):
    # There is no user-supplied SQL route. Guard every internal statement as well.
    if not sql.lstrip().upper().startswith('SELECT ') or ';' in sql:
        raise RuntimeError('Only SELECT is permitted')
    return await execute_sql(sql, args)


async def execute_sql(sql, args=None):
    global _metadata_epoch
    mutation = not sql.lstrip().upper().startswith('SELECT ')
    if mutation:
        _metadata_epoch += 1
        _metadata_cache.clear()
    url, token = endpoint()
    try:
        client = _request_client.get()
        owned = client is None
        if owned:
            client = httpx.AsyncClient(timeout=35, follow_redirects=False)
        try:
            res = await client.post(url, headers={'Authorization': 'Bearer ' + token}, json={'requests': [{'type': 'execute', 'stmt': {'sql': sql, 'args': [{'type':'null'} if v is None else {'type': 'integer', 'value': str(v)} if isinstance(v, int) else {'type':'float','value':v} if isinstance(v,float) else {'type': 'text', 'value': str(v)} for v in (args or [])], 'want_rows': True}}, {'type': 'close'}]})
        finally:
            if owned:
                await client.aclose()
            if mutation:
                _metadata_epoch += 1
                _metadata_cache.clear()
        if res.status_code in (401, 403):
            raise HTTPException(502, 'Turso 拒絕連線，請核對 URL 與 Token 是否屬於同一個資料庫。')
        if res.status_code != 200:
            raise HTTPException(502, 'Turso 連線失敗（HTTP ' + str(res.status_code) + '）。')
        payload = res.json()
        error = payload.get('results', [{}])[0]
        if error.get('type') == 'error':
            message = str(error.get('error', {}).get('message', '')).lower()
            if 'unique' in message or 'constraint_unique' in message:
                raise HTTPException(409, '相同網址或識別碼已存在。請搜尋既有項目後編輯。')
            if 'readonly' in message or 'read-only' in message:
                raise HTTPException(403, 'Turso Token 只有唯讀權限，請在 Vercel 設定可寫入的 Token 並重新部署。')
            raise HTTPException(502, '資料庫未接受操作，請檢查權限與欄位結構。資料未確認儲存。')
        return decode_result(payload)
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, 'Turso 暫時無法讀取或回應格式不符；請稍後重新載入。') from None


# SQL normalization keeps all filtering before LIMIT, without a database migration.
MODULE_TABLES = {'mono': ['articles', 'custom_resources'],
                 'bib': ['academic_pubs', 'bibliography_notes', 'custom_resources'],
                 'media': ['media_vault', 'custom_resources'], 'omni': ['omni_vault']}
FIELDS = ['id','type','title','author','source','category','notes','summary','url','image',
          'identifier','published','issue','volume','rating','shelf','stage','saved','news','added','pubtype']
_schema_cache = {}


def ident(value):
    return '"' + value.replace('"', '""') + '"'


async def schema():
    # Cache table metadata only, never user content; isolate databases/tokens.
    key = hashlib.sha256((os.getenv('TURSO_DATABASE_URL','') + os.getenv('TURSO_AUTH_TOKEN','')).encode()).hexdigest()
    entry = _schema_cache.get(key)
    if entry and time.time() - entry[0] < 60:
        return entry[1]
    _, tables = await query("SELECT name FROM sqlite_master WHERE type='table'")
    existing = {r['name'] for r in tables}
    result = {}
    for table in TABLES:
        if table in existing:
            cols, _ = await query(f'SELECT * FROM {ident(table)} LIMIT 0')
            result[table] = {c.lower(): c for c in cols}
    _schema_cache.clear()
    _schema_cache[key] = (time.time(), result)
    return result


def normalized_select(table, cols, module):
    def col(*names, default="''"):
        choices = [ident(cols[n]) for n in names if n in cols]
        return 'COALESCE(' + ','.join(choices + [default]) + ')' if choices else default
    def text(*names, default="''"):
        return f'CAST({col(*names, default=default)} AS TEXT)'
    values = {k: "''" for k in FIELDS}
    # Each original table has an id or unique link/identifier; no synthetic offset IDs.
    key = text('id','link','identifier','url','source_url')
    values.update(id=f"'{table}:' || {key}", title=text('title',default="'未命名'"),
                  author=text('author'), source=text('source'), category=text('category',default="'未分類'"),
                  notes=text('comment','notes'), summary=text('summary','abstract'),
                  url=text('url','link','source_url'), image=text('image','image_url','cover_image'),
                  identifier=text('identifier'), published=text('publish_date','release_date','published'),
                  issue=text('issue_volume'), rating=text('importance',default="'待讀'"),
                  added=text('added_date','created_at','sortdate','sort_date','publish_date'),
                  saved=f"CASE WHEN CAST({col('is_bookmarked',default='0')} AS INTEGER) = 1 THEN 1 ELSE 0 END", news='0')
    status=col('book_status',default='0')
    values['shelf']=f"CASE CAST({status} AS INTEGER) WHEN 1 THEN '待讀書架' WHEN 2 THEN '已讀書籍' WHEN 3 THEN '實體書庫' WHEN 4 THEN '電子書架' ELSE '未入書庫' END"
    values['stage']=f"CASE WHEN CAST({col('is_bookmarked',default='0')} AS INTEGER) = 1 THEN '待播' ELSE '典藏' END"
    where=''
    if table == 'articles':
        values['type']="'article'"
        news=['WIRED.jp','CINRA','VERSE','界面文化','Radii','触乐','FNMNL']
        condition=' OR '.join(f"instr(lower({values['source']}),lower('{v}')) > 0" for v in news)
        values['news']=f'CASE WHEN {condition} THEN 1 ELSE 0 END'
    elif table == 'academic_pubs':
        values['type']=f"CASE {col('type')} WHEN 'Web Link' THEN 'bibLink' WHEN 'Journal' THEN 'journal' ELSE 'book' END"
        values['source']=text('publisher_journal')
    elif table == 'bibliography_notes':
        values['type']="'reference'"
        values['source']=text('publisher_journal')
        values['notes']=text('notes')
        values['pubtype']=f"CASE {col('type')} WHEN 'Journal' THEN '期刊論文' ELSE '專書' END"
    elif table == 'media_vault':
        values['type']="'media'"
        values['author']=text('creator')
        mt=text('media_type')
        values['category']=f"CASE WHEN {mt} LIKE '%電影%' OR {mt} LIKE '%影集%' OR {mt} LIKE '%Movie%' OR {mt} LIKE '%TV%' THEN '電影與影集' ELSE '音樂與專輯' END"
    elif table == 'omni_vault':
        values['type']="'omni'"
    else:
        mod=text('module')
        mappings={'mono':("'monoResource'", "'未來典藏'", "'monoreader'"),
                  'bib':("'bibResource'", f"CASE {mod} WHEN 'biblioapp_lecture' THEN '講座記錄' WHEN 'biblioapp_conference' THEN '學術會議' ELSE '網路資源' END", "'biblioapp','biblioapp_lecture','biblioapp_conference'"),
                  'media':("'mediaResource'", "'網路資源分享卡'", "'media_vault'")}
        values['type'],values['category'],modules=mappings[module]
        where=f' WHERE {mod} IN ({modules})'
    return 'SELECT '+','.join(f'{values[k]} AS {ident(k)}' for k in FIELDS)+f' FROM {ident(table)}'+where


async def module_sql(module):
    if module not in MODULE_TABLES:
        raise HTTPException(400, '不支援的模組。')
    cols = await schema()
    parts = [normalized_select(t,cols[t],module) for t in MODULE_TABLES[module] if t in cols]
    if not parts:
        return 'SELECT '+','.join("'' AS "+ident(k) for k in FIELDS)+' WHERE 0'
    return ' UNION ALL '.join(parts)


def conditions(module, tab, sub, folder, q):
    where=[]; args=[]
    def eq(field,value):
        where.append(ident(field)+' = ?'); args.append(value)
    if tab == '搜尋中心':
        if not q.strip():
            where.append('0')
    elif module == 'mono':
        eq('type','monoResource' if tab == '未來典藏' else 'article')
        if tab in ('全部來源總覽','最新評論','文化快訊'):
            where.append("julianday(added) BETWEEN julianday('now','-24 hours') AND julianday('now')")
        if tab == '最新評論': eq('news',0)
        if tab == '文化快訊': eq('news',1)
        if tab == '我的收藏庫': eq('saved',1)
    elif module == 'bib':
        if tab == '個人書庫':
            where.append("type IN ('book','journal')"); eq('shelf',sub)
        elif tab == '參考書目': eq('type','reference')
        elif tab == '網址備存': eq('type','bibLink')
        elif tab == '可用資源': eq('type','bibResource'); eq('category',sub)
        else: eq('type','journal' if sub == '期刊論文' else 'book')
    elif module == 'media':
        if sub == '網路資源分享卡': eq('type','mediaResource')
        else:
            eq('type','media'); eq('category',sub)
            eq('stage','典藏' if tab == '典藏／已完成' else '待播')
    elif module == 'omni' and folder: eq('category',folder)
    if q.strip():
        # Literal substring search: SQL metacharacters in user text have no effect.
        fields=['title','author','source','category','notes','summary','identifier','issue','url']
        where.append('('+' OR '.join(f'instr(lower({ident(k)}),lower(?)) > 0' for k in fields)+')')
        args.extend([q.strip()]*len(fields))
    return where,args


JOURNAL_ROOTS = ('e-flux Journal', 'The Funambulist', 'The Point', '421 News', 'TripleAmpersand', 'Metode', 'FRIEZE')


def source_group(source):
    for root in JOURNAL_ROOTS:
        if source.lower() == root.lower() or source.lower().startswith(root.lower() + ' ('):
            return root, True
    match = re.match(r'^(.*?)\s*\((?:Issue|Vol\.?|No\.?)\s*\d+', source, re.I)
    return (match.group(1).strip(), True) if match else (source, False)


def issue_order(source, added=''):
    root, _ = source_group(source)
    suffix = source[len(root):]
    match = re.search(r'(?:Issue|No\.?|#)\s*#?\s*(\d+)', suffix, re.I) or re.search(r'\((\d+)\)', suffix)
    # Numeric issue ordering: 110 > 10 > 2, independent of ingestion date.
    return (1 if match else 0, int(match.group(1)) if match else 0, added or '', source)



PUBLISHERS = {
 '青土社':['青土社','Seidosha'],
 '東京大學出版會':['東京大學出版會','東京大学出版会','University of Tokyo Press'],
 'Duke University Press':['Duke University Press','Duke','Duke University Press (DUP)'],
 'Verso':['Verso','Verso Books'],
 'MIT Press':['MIT Press','The MIT Press'],
}

def source_expr():
    cases=[]
    for name,aliases in PUBLISHERS.items():
        quoted=','.join("'"+v.lower().replace("'","''")+"'" for v in aliases)
        cases.append("WHEN lower(trim(source)) IN ("+quoted+") THEN '"+name+"'")
    return "CASE "+" ".join(cases)+" ELSE COALESCE(NULLIF(trim(source),''),'未標明來源') END"

def date_expr(field):
    value='trim('+ident(field)+')'
    return f"""julianday(CASE
      WHEN {value} GLOB '[0-9][0-9][0-9][0-9]' THEN {value} || '-01-01'
      WHEN {value} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]' THEN {value} || '-01'
      WHEN length({value}) >= 10 THEN {value}
      ELSE NULL END)"""

def issue_expr():
    return """CASE WHEN trim(issue) != '' THEN 'issue:' || trim(issue)
     WHEN substr(published,1,7) GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]' THEN 'month:' || substr(published,1,7)
     WHEN trim(published) GLOB '[0-9][0-9][0-9][0-9]' THEN 'year:' || trim(published)
     ELSE 'unknown:' END"""

@app.get('/api/explore')
async def explore(request: Request, source: str='', q: str=''):
    require_login(request)
    if len(source)>500 or len(q)>500:raise HTTPException(400,'查詢過長。')
    sql=await module_sql('bib')
    src=source_expr()
    if not source:
        _,rows=await query(f"SELECT type,{src} AS name,count(*) AS total FROM ({sql}) WHERE type IN ('book','journal') AND instr(lower({src}),lower(?))>0 GROUP BY type,{src} ORDER BY name COLLATE NOCASE",[q.strip()])
        publishers=[{'name':name,'total':sum(int(r['total']) for r in rows if r['type']=='book' and r['name']==name)} for name in PUBLISHERS if not q.strip() or q.strip().lower() in name.lower() or any(q.strip().lower() in a.lower() for a in PUBLISHERS[name])]
        other=[r for r in rows if r['type']=='book' and r['name'] not in PUBLISHERS]
        journals=[r for r in rows if r['type']=='journal']
        return {'publishers':publishers,'other_publishers':other,'journal_folders':journals,'items':[]}
    key=issue_expr()
    _,rows=await query(f"SELECT {key} AS key,count(*) AS total,MAX({date_expr('published')}) AS newest FROM ({sql}) WHERE type='journal' AND {src}=? GROUP BY {key}",[source])
    for row in rows:
        prefix,value=row['key'].split(':',1)
        row['label']={'issue':value,'month':'出版年月 '+value,'year':'出版年份 '+value,'unknown':'未標明期號／日期'}[prefix]
    def ordering(row):
        nums=tuple(int(n) for n in re.findall(r'\d+',row['key']))
        return (row['newest'] is not None,row['newest'] or 0,nums,row['label'])
    rows.sort(key=ordering,reverse=True)
    if q.strip():rows=[r for r in rows if q.strip().lower() in r['label'].lower()]
    return {'issue_folders':rows,'items':[]}

@app.get('/api/browse')
async def browse(request: Request, module: str='mono', tab: str='全部來源總覽',
                 sub: str='', folder: str='', q: str='', source: str='全部',
                 issue: str='全部', sort: str='added', asc: bool=False, page: int=1, bsource: str='', bissue: str=''):
    require_login(request)
    if page < 1 or page > 1000000 or any(len(v)>500 for v in (q,source,issue,folder,tab,sub,bsource,bissue)):
        raise HTTPException(400,'查詢參數超出範圍。')
    if sort not in ('added','title','published','author','category','rating'):
        raise HTTPException(400,'不支援的排序。')
    sql=await module_sql(module)
    where,args=conditions(module,tab,sub,folder,q)
    if module=='bib' and tab=='文獻探索' and bsource:
        where.append(source_expr()+' = ?');args.append(bsource)
        if bissue:
            where.append(issue_expr()+' = ?');args.append(bissue)
    base=f'SELECT * FROM ({sql}) WHERE '+(' AND '.join(where) or '1')
    field='source' if module=='mono' or (module=='bib' and tab=='文獻探索') else 'category'
    journals=[]; selected_issue=''; grouped=False
    if module == 'mono' and tab != '未來典藏':
        # Keep the folder/issue directory stable while searching within an issue.
        facet_where,facet_args=conditions(module,tab,sub,folder,'')
        if tab == '搜尋中心': facet_where=[]
        facet_base=f'SELECT * FROM ({sql}) WHERE '+(' AND '.join(facet_where) or '1')
        _,raw_sources=await cached_metadata(f"SELECT source AS value, MAX(added) AS added FROM ({facet_base}) WHERE source != '' GROUP BY source ORDER BY source COLLATE NOCASE",facet_args)
        groups={}
        for row in raw_sources:
            name,is_journal=source_group(row['value'])
            group=groups.setdefault(name,{'name':name,'folder':is_journal,'members':[]})
            group['members'].append(row)
        for group in groups.values():
            group['members'].sort(key=lambda r:issue_order(r['value'],r['added']),reverse=True)
            if group['folder']:
                journals.append({'name':group['name'],'issues':len(group['members']),'latest':group['members'][0]['value']})
        fs=[{'value':name} for name in sorted(groups,key=str.casefold)]
        fi=[]
        if source != '全部':
            group=groups.get(source)
            if group and group['folder']:
                grouped=True
                members=[r['value'] for r in group['members']]
                fi=[{'value':v} for v in members]
                if issue == '最新': selected_issue=members[0]
                elif issue != '全部': selected_issue=issue
                if selected_issue:
                    if selected_issue not in members: raise HTTPException(400,'此期號不屬於所選雜誌。')
                    base+=' AND source = ?'; args=args+[selected_issue]
                else:
                    base+=' AND source IN ('+','.join('?' for _ in members)+')';args=args+members
            else:
                base+=' AND source = ?';args=args+[source]
    else:
        _,fs=await cached_metadata(f'SELECT DISTINCT {ident(field)} AS value FROM ({base}) WHERE {ident(field)} != \'\' ORDER BY value COLLATE NOCASE',args)
        if source!='全部': base+=f' AND {ident(field)} = ?'; args=args+[source]
        _,fi=await cached_metadata(f"SELECT DISTINCT issue AS value FROM ({base}) WHERE issue != '' ORDER BY value COLLATE NOCASE",args)
        if issue!='全部': base+=' AND issue = ?'; args=args+[issue]
    _,counts=await cached_metadata(f'SELECT COUNT(*) AS total FROM ({base})',args)
    total=int(counts[0]['total'])
    shelf_view = (module == 'bib' and (tab == '個人書庫' or (tab == '文獻探索' and sub != '期刊論文'))) or (module == 'media' and tab != '搜尋中心' and sub != '網路資源分享卡')
    size = 18 if shelf_view else 30
    page=min(page,max(1,(total+size-1)//size))
    order=f'{ident(sort)} COLLATE NOCASE'
    if sort in ('added','published'): order=date_expr(sort)
    if sort=='rating':
        order="CASE rating "+' '.join(f"WHEN '{v}' THEN {i}" for i,v in enumerate(['S','A','A-','B','B-','C','C-','待讀']))+' ELSE 99 END'
    # Trim only display payloads, after filtering/searching full text in SQL.
    projected=[]
    for k in FIELDS:
        if k in ('notes','summary'): projected.append(f'substr({k},1,1200) AS {k}')
        elif k=='image': projected.append("CASE WHEN length(image)<=30000 THEN image ELSE '' END AS image")
        else: projected.append(ident(k))
    _,items=await query('SELECT '+','.join(projected)+f' FROM ({base}) ORDER BY ({order}) IS NULL, {order} '+('ASC' if asc else 'DESC')+', id ASC LIMIT ? OFFSET ?',args+[size,(page-1)*size])
    for item in items:
        if not item.get('image'):
            item['image']='/api/image?module='+quote(module)+'&id='+quote(item['id'],safe='')
    return {'items':items,'total':total,'page':page,'page_size':size,
            'sources':[r['value'] for r in fs],'issues':[r['value'] for r in fi],
            'journals':journals,'grouped_source':grouped,'selected_issue':selected_issue,
            'checked_at':int(time.time()),'version':'editing-pwa-v9'}


@app.get('/api/folders')
async def folder_list(request: Request, q: str=''):
    require_login(request)
    if len(q)>500: raise HTTPException(400,'搜尋文字過長。')
    sql=await module_sql('omni')
    _,rows=await query(f"SELECT category AS name, COUNT(*) AS total, MAX(CASE WHEN length(image)<=30000 THEN image ELSE '' END) AS image FROM ({sql}) WHERE instr(lower(category),lower(?))>0 GROUP BY category ORDER BY category COLLATE NOCASE",[q.strip()])
    return {'folders':rows,'checked_at':int(time.time())}


@app.get('/api/item')
async def item_detail(request: Request, module: str, id: str):
    require_login(request)
    if len(id)>4000: raise HTTPException(400,'識別碼過長。')
    sql=await module_sql(module)
    _,rows=await query(f'SELECT * FROM ({sql}) WHERE id = ? LIMIT 1',[id])
    if not rows: raise HTTPException(404,'找不到此項目，請重新整理清單。')
    if len(json.dumps(rows[0],ensure_ascii=False).encode())>3500000:
        raise HTTPException(413,'這筆資料過大，請暫時使用原網站查看。')
    result=rows[0]
    table,key,colname,raw=await raw_item(module,id)
    result['_revision']=revision(raw)
    result['_editable']=list(edit_mapping(table,await schema()).keys())
    result['_writes']=writes_enabled()
    return result


@app.get('/api/stats')
async def stats(request: Request):
    require_login(request)
    cols=await schema(); results={}
    for table in TABLES:
        if table not in cols: results[table]=None; continue
        _,rows=await query(f'SELECT COUNT(*) AS total FROM {ident(table)}')
        results[table]=int(rows[0]['total'])
    return results

@app.get('/api/session')
def session_status(request: Request):
    require_login(request)
    return {'authenticated': True}

# V5 deliberately has no DELETE endpoint or database migration.
def writes_enabled():
    return os.getenv('ENABLE_WRITES','').strip().lower() == 'true'


def write_auth(request):
    require_login(request)
    # Browser mutations must have a verified Origin; don't accept absent/null origins.
    if not request.headers.get('origin'):
        raise HTTPException(403,'請從 App 頁面提交修改。')
    check_origin(request)
    if not writes_enabled():
        raise HTTPException(403,'寫入尚未啟用。請設定 ENABLE_WRITES=true 後重新部署。')


async def body_json(request):
    body=await request.body()
    if len(body)>250000: raise HTTPException(413,'一次輸入資料過長，請縮短內容。')
    try:
        data=json.loads(body)
    except (ValueError,TypeError): raise HTTPException(400,'提交格式不正確。') from None
    if not isinstance(data,dict): raise HTTPException(400,'提交格式不正確。')
    return data


WRITE_FIELDS={
 'articles':{'title':['title'],'source':['source'],'url':['link'],'image':['image'],'summary':['summary'],'notes':['comment','notes'],'saved':['is_bookmarked']},
 'academic_pubs':{'title':['title'],'author':['author'],'source':['publisher_journal'],'category':['category'],'notes':['comment','notes'],'summary':['abstract'],'url':['link'],'image':['image'],'identifier':['identifier'],'published':['publish_date'],'issue':['issue_volume'],'shelf':['book_status']},
 'bibliography_notes':{'title':['title'],'author':['author'],'source':['publisher_journal'],'notes':['notes'],'url':['link'],'identifier':['identifier'],'published':['publish_date'],'issue':['issue_volume'],'rating':['importance'],'pubtype':['type']},
 'media_vault':{'title':['title'],'author':['creator'],'notes':['comment','notes'],'summary':['summary'],'url':['source_url'],'image':['cover_image'],'published':['release_date'],'stage':['is_bookmarked']},
 'omni_vault':{'title':['title'],'category':['category'],'notes':['comment','notes'],'url':['url'],'image':['image_url']},
 'custom_resources':{'title':['title'],'notes':['comment','notes'],'url':['url']},
}


def edit_mapping(table, schemas):
    cols=schemas.get(table,{})
    # Keys used to locate rows must stay stable if the table has no numeric id.
    mapping={field:next((cols[k] for k in choices if k in cols),None) for field,choices in WRITE_FIELDS[table].items()}
    if 'id' not in cols:
        mapping.pop('url',None);mapping.pop('identifier',None)
    return {k:v for k,v in mapping.items() if v}


def revision(raw):
    return signature('row:'+json.dumps(raw,ensure_ascii=False,sort_keys=True,separators=(',',':')))


async def raw_item(module,id):
    if not isinstance(id,str) or len(id)>5000 or ':' not in id:
        raise HTTPException(400,'項目識別碼不正確。')
    table,key=id.split(':',1)
    if not isinstance(module,str) or table not in MODULE_TABLES.get(module,[]): raise HTTPException(400,'項目不屬於此模組。')
    schemas=await schema();cols=schemas.get(table,{})
    colname=next((cols[k] for k in ('id','link','identifier','url','source_url') if k in cols),None)
    if not colname: raise HTTPException(404,'找不到資料表或識別欄位。')
    _,rows=await query(f'SELECT * FROM {ident(table)} WHERE {ident(colname)} = ? LIMIT 1',[key])
    if not rows: raise HTTPException(404,'項目已不存在，請更新清單。')
    raw=rows[0]
    if table=='custom_resources':
        allowed={'mono':['monoreader'],'bib':['biblioapp','biblioapp_lecture','biblioapp_conference'],'media':['media_vault']}
        if raw.get(cols.get('module','module')) not in allowed.get(module,[]):
            raise HTTPException(400,'資源不屬於此模組。')
    return table,key,colname,raw


def checked_value(field,value):
    if field=='saved':
        if not isinstance(value,bool): raise HTTPException(400,'收藏狀態格式不正確。')
        return int(value)
    choices={'shelf':{'未入書庫':0,'待讀書架':1,'已讀書籍':2,'實體書庫':3,'電子書架':4},
             'stage':{'待播':1,'典藏':0},'rating':{v:v for v in ['S','A','A-','B','B-','C','C-','待讀']},
             'pubtype':{'專書':'Book','期刊論文':'Journal'}}
    if field in choices:
        if not isinstance(value,str) or value not in choices[field]: raise HTTPException(400,'不支援的分類或狀態。')
        return choices[field][value]
    if not isinstance(value,str): raise HTTPException(400,'文字欄位格式不正確。')
    limit=50000 if field in ('notes','summary') else 4000 if field in ('url','image') else 1000
    if len(value)>limit: raise HTTPException(400,f'{field} 文字超過 {limit} 字元。')
    if field in ('title','category') and not value.strip(): raise HTTPException(400,'名稱與分類不能留空。')
    if field in ('url','image') and value:
        u=urlsplit(value)
        if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:
            raise HTTPException(400,'網址必須是有效的 http:// 或 https:// 網址。')
    return value if field in ('notes','summary') else value.strip()


async def write_query(sql,args):
    if not (sql.startswith('UPDATE "') or sql.startswith('INSERT INTO "') or sql.startswith('DELETE FROM "')) or ';' in sql:
        raise RuntimeError('Unsupported write statement')
    return await execute_sql(sql,args)


@app.post('/api/update')
async def update_item(request: Request):
    write_auth(request);data=await body_json(request)
    module=data.get('module');table,key,keycol,raw=await raw_item(module,data.get('id'))
    ver=data.get('revision')
    if not isinstance(ver,str) or not hmac.compare_digest(ver,revision(raw)):
        raise HTTPException(409,'這筆資料已在其他裝置或程式更新。請保留你的文字，關閉後重新開啟最新內容再修改。')
    changes=data.get('changes')
    if not isinstance(changes,dict) or not changes: raise HTTPException(400,'沒有提交修改。')
    mapping=edit_mapping(table,await schema())
    if any(k not in mapping for k in changes):
        raise HTTPException(400,'原資料表沒有這個可編輯欄位。本版不會自動新增欄位。')
    values={mapping[k]:checked_value(k,v) for k,v in changes.items()}
    # Atomic comparison prevents a concurrent writer overwriting any edited field
    # between the read above and this UPDATE, without needing a schema migration.
    guards=[f'{ident(keycol)} = ?'];args=list(values.values())+[key]
    for col in values:
        guards.append(f'{ident(col)} IS ?');args.append(raw[col])
    sql=f'UPDATE {ident(table)} SET '+','.join(f'{ident(k)} = ?' for k in values)+' WHERE '+' AND '.join(guards)+f' RETURNING {ident(keycol)}'
    _,rows=await write_query(sql,args)
    if not rows: raise HTTPException(409,'資料剛被修改，這次未儲存。請重新開啟最新內容後再試。')
    return {'ok':True,'message':'已儲存至 Turso'}


CREATE_TYPES={'article':('mono','articles'),'monoResource':('mono','custom_resources'),
 'book':('bib','academic_pubs'),'journal':('bib','academic_pubs'),'bibLink':('bib','academic_pubs'),
 'reference':('bib','bibliography_notes'),'bibResource':('bib','custom_resources'),
 'media':('media','media_vault'),'mediaResource':('media','custom_resources'),'omni':('omni','omni_vault')}


@app.post('/api/create')
async def create_item(request: Request):
    write_auth(request);data=await body_json(request);kind=data.get('type')
    if not isinstance(kind,str) or kind not in CREATE_TYPES: raise HTTPException(400,'不支援的項目類型。')
    module,table=CREATE_TYPES[kind]
    if data.get('module')!=module: raise HTTPException(400,'模組與類型不符。')
    fields=data.get('fields')
    if not isinstance(fields,dict) or not isinstance(fields.get('title'),str) or not fields['title'].strip(): raise HTTPException(400,'請填寫名稱。')
    schemas=await schema();cols=schemas.get(table)
    if not cols: raise HTTPException(400,'原資料庫沒有此資料表，請先確認資料庫結構。')
    mapping={k:next((cols[c] for c in names if c in cols),None) for k,names in WRITE_FIELDS[table].items()}
    if any(k not in WRITE_FIELDS[table] for k in fields): raise HTTPException(400,'包含不支援的欄位。')
    values={}
    for k,v in fields.items():
        if not mapping.get(k):
            if v not in ('',None): raise HTTPException(400,f'原資料表沒有 {k} 欄位，未建立項目；請先移除該欄內容。')
            continue
        values[mapping[k]]=checked_value(k,v)
    now=datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    manual='manual:'+uuid.uuid4().hex
    def put(name,value,default=False):
        if name in cols and (not default or cols[name] not in values): values[cols[name]]=value
    put('created_at',now);put('added_date',now);put('sortdate',now);put('sort_date',now)
    if table=='articles':
        if not fields.get('url'): raise HTTPException(400,'新增文章必須填寫原文網址。')
        put('source','外部手動匯入',True);put('published','手動收藏',True);put('is_bookmarked',1,True)
    if table=='academic_pubs':
        put('type',{'book':'Book','journal':'Journal','bibLink':'Web Link'}[kind]);put('is_manual',1)
        if not fields.get('identifier'):put('identifier',manual)
        put('book_status',1,True);put('category','未分類',True);put('publish_date',now[:10],True)
    if table=='bibliography_notes':
        put('type','Book',True);put('importance','待讀',True)
        if not fields.get('identifier'):put('identifier',manual)
    if table=='media_vault':
        category=data.get('category','電影與影集')
        if category not in ('電影與影集','音樂與專輯'): raise HTTPException(400,'影音類型不正確。')
        put('media_type','電影' if category=='電影與影集' else '音樂專輯');put('is_bookmarked',1,True)
        if not fields.get('url'):put('source_url',manual)
    if table=='omni_vault': put('category','未分類',True)
    if table=='custom_resources':
        resource_module={'monoResource':'monoreader','mediaResource':'media_vault'}.get(kind)
        if kind=='bibResource':
            resource_module={'網路資源':'biblioapp','講座記錄':'biblioapp_lecture','學術會議':'biblioapp_conference'}.get(data.get('category','網路資源'))
        if not resource_module: raise HTTPException(400,'資源分類不正確。')
        put('module',resource_module)
        if not fields.get('url'):put('url',manual)
    keycol=next((cols[k] for k in ('id','link','identifier','url','source_url') if k in cols),None)
    if not keycol: raise HTTPException(400,'缺少項目識別欄位。')
    sql=f'INSERT INTO {ident(table)} ('+','.join(ident(k) for k in values)+') VALUES ('+','.join('?' for _ in values)+f') RETURNING {ident(keycol)}'
    _,rows=await write_query(sql,list(values.values()))
    return {'ok':True,'id':table+':'+str(rows[0][keycol]),'message':'已新增至 Turso'}

@app.get('/api/capabilities')
async def capabilities(request: Request):
    require_login(request);schemas=await schema()
    return {'writes':writes_enabled(),'types':{kind:[field for field,names in WRITE_FIELDS[table].items() if any(n in schemas.get(table,{}) for n in names)] for kind,(module,table) in CREATE_TYPES.items() if table in schemas}}

@app.post('/api/bookmark')
async def bookmark(request: Request):
    write_auth(request)
    data=await body_json(request)
    if not isinstance(data.get('saved'),bool): raise HTTPException(400,'收藏狀態格式不正確。')
    table,key,keycol,raw=await raw_item('mono',data.get('id'))
    if table != 'articles': raise HTTPException(400,'此按鈕只用於文章收藏。')
    column=edit_mapping(table,await schema()).get('saved')
    if not column: raise HTTPException(400,'資料表沒有收藏欄位。')
    # Explicit desired state is idempotent; only this column is updated, not notes.
    _,rows=await write_query(f'UPDATE {ident(table)} SET {ident(column)} = ? WHERE {ident(keycol)} = ? RETURNING {ident(keycol)}',[int(data['saved']),key])
    if not rows: raise HTTPException(404,'此文章已不存在。')
    return {'ok':True,'saved':data['saved']}


@app.post('/api/lookup')
async def metadata_lookup(request: Request):
    write_auth(request)
    data=await body_json(request)
    from metadata import lookup_metadata
    # Lookup only returns a draft. Saving is a separate, explicit /api/create call.
    return await lookup_metadata(data.get('kind'),data.get('value'))


# Public PWA assets only. No arbitrary file access or authenticated-page cache.
PWA_TYPES = {"manifest.webmanifest": "application/manifest+json", "sw.js": "application/javascript", "pwa.js": "application/javascript", "offline.html": "text/html", "icon-192.png": "image/png", "icon-512.png": "image/png", "maskable-512.png": "image/png", "apple-touch-icon.png": "image/png"}

@app.get('/{asset}', include_in_schema=False)
def pwa_asset(asset: str):
    if asset not in PWA_TYPES:
        raise HTTPException(404)
    return FileResponse(ROOT / 'pwa' / asset, media_type=PWA_TYPES[asset], headers={"Service-Worker-Allowed": "/"} if asset == "sw.js" else {})

@app.get('/api/image')
async def item_image(request: Request, module: str, id: str):
    require_login(request)
    sql=await module_sql(module)
    _, rows=await query(f'SELECT image FROM ({sql}) WHERE id = ? LIMIT 1',[id])
    value=rows[0]['image'] if rows else ''
    match=re.fullmatch(r'data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=\s]+)',value or '')
    if not match: raise HTTPException(404,'沒有內嵌圖片。')
    try: data=base64.b64decode(match[2],validate=False)
    except ValueError: raise HTTPException(404,'圖片格式無效。')
    return Response(data,media_type='image/'+match[1],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@app.get('/api/categories')
async def categories(request: Request, module: str):
    require_login(request)
    sql=await module_sql(module)
    _, rows=await query(f"SELECT DISTINCT category FROM ({sql}) WHERE category != '' ORDER BY category COLLATE NOCASE")
    defaults=['未分類','研究','學術','小說','詩','次文化','藝術','音樂'] if module=='bib' else ['未分類']
    return {'categories':list(dict.fromkeys(defaults+[r['category'] for r in rows]))}

@app.get('/api/crawler-health')
async def crawler_health(request: Request):
    require_login(request)
    _, tables=await query("SELECT name FROM sqlite_master WHERE type='table' AND name='crawler_health'")
    if not tables: return {'available':False,'items':[],'alerts':0}
    _, rows=await query('SELECT source_name,status,last_check,error_msg FROM crawler_health ORDER BY source_name')
    alerts=0
    for row in rows:
        try:
            dt=datetime.fromisoformat((row.get('last_check') or '').replace('Z','+00:00'))
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            hours=max(0,(datetime.now(timezone.utc)-dt).total_seconds()/3600)
        except (ValueError,TypeError): hours=None
        row['hours']=round(hours,1) if hours is not None else None
        row['alert']=row.get('status') in ('EMPTY','ERROR') and hours is not None and hours>48
        alerts+=int(row['alert'])
    return {'available':True,'items':rows,'alerts':alerts,'checked_at':int(time.time())}


@app.post('/api/delete')
async def delete_item(request: Request):
    write_auth(request)
    data=await body_json(request)
    if data.get('confirmed') is not True:
        raise HTTPException(400,'請先勾選確認刪除。')
    table,key,keycol,raw=await raw_item(data.get('module'),data.get('id'))
    ver=data.get('revision')
    if not isinstance(ver,str) or not hmac.compare_digest(ver,revision(raw)):
        raise HTTPException(409,'資料已變更，未刪除。請重新開啟最新資料再確認。')
    # Compare the entire row atomically, including fields edited by Streamlit.
    guards=[ident(col)+' IS ?' for col in raw]
    _,rows=await write_query('DELETE FROM '+ident(table)+' WHERE '+' AND '.join(guards)+' RETURNING '+ident(keycol),list(raw.values()))
    if not rows: raise HTTPException(409,'資料剛被修改，未刪除。請重新讀取。')
    return {'ok':True,'message':'已刪除條目'}
