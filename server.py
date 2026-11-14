"""Monoreader connection milestone. Authenticated SELECT-only service."""
import json
import hashlib
import hmac
import os
import time
from collections import deque
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
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
    response.headers['X-Monoreader-Version'] = 'layout-v4'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    # Native HTML form POSTs can send Origin: null under no-referrer.
    # Preserve the origin for our login/logout CSRF checks.
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


LOGIN = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Monoreader 登入</title><style>body{background:#f5f3ed;color:#233e38;font:16px/1.7 system-ui;display:grid;place-items:center;min-height:90vh;margin:20px}main{max-width:380px;width:100%}h1{font-family:Georgia,serif;font-size:40px}input,button{box-sizing:border-box;width:100%;padding:14px;font:inherit;margin:10px 0;border:1px solid #c5cec1;border-radius:8px}button{background:#233e38;color:white}p{color:#657268;font-size:14px}</style><main><h1>monoreader</h1><p>完整分頁與搜尋 · 唯讀版本</p><form method="post" action="/login"><label for="password">你設定的 App 登入密碼</label><input id="password" type="password" name="password" required autocomplete="current-password" maxlength="512"><button>登入</button></form><p>密碼是在 Vercel 的 APP_PASSWORD 設定，不是 GitHub 或 Turso 密碼。</p></main><script>try{for(const k of Object.keys(localStorage)){if(k.startsWith('monoreader-pages-'))localStorage.removeItem(k)}}catch(e){}</script></html>'''


@app.get('/health')
def health():
    return {'status': 'running', 'mode': 'read-only', 'version': 'layout-v4'}


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
    boot = {'expires': expires, 'cacheKey': signature('cache-v4:' + os.getenv('TURSO_DATABASE_URL', ''))[:32]}
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
    url, token = endpoint()
    try:
        async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
            res = await client.post(url, headers={'Authorization': 'Bearer ' + token}, json={'requests': [{'type': 'execute', 'stmt': {'sql': sql, 'args': [{'type': 'integer', 'value': str(v)} if isinstance(v, int) else {'type': 'text', 'value': str(v)} for v in (args or [])], 'want_rows': True}}, {'type': 'close'}]})
        if res.status_code in (401, 403):
            raise HTTPException(502, 'Turso 拒絕連線，請核對 URL 與 Token 是否屬於同一個資料庫。')
        if res.status_code != 200:
            raise HTTPException(502, 'Turso 連線失敗（HTTP ' + str(res.status_code) + '）。')
        return decode_result(res.json())
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
                  identifier=text('identifier'), published=text('publish_date','release_date'),
                  issue=text('issue_volume'), rating=text('importance',default="'待讀'"),
                  added=text('added_date','sortdate','sort_date','publish_date'),
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


@app.get('/api/browse')
async def browse(request: Request, module: str='mono', tab: str='全部來源總覽',
                 sub: str='', folder: str='', q: str='', source: str='全部',
                 issue: str='全部', sort: str='added', asc: bool=False, page: int=1):
    require_login(request)
    if page < 1 or page > 1000000 or any(len(v)>500 for v in (q,source,issue,folder,tab,sub)):
        raise HTTPException(400,'查詢參數超出範圍。')
    if sort not in ('added','title','published','author','category','rating'):
        raise HTTPException(400,'不支援的排序。')
    sql=await module_sql(module)
    where,args=conditions(module,tab,sub,folder,q)
    base=f'SELECT * FROM ({sql}) WHERE '+(' AND '.join(where) or '1')
    field='source' if module=='mono' or (module=='bib' and tab=='文獻探索') else 'category'
    _,fs=await query(f'SELECT DISTINCT {ident(field)} AS value FROM ({base}) WHERE {ident(field)} != \'\' ORDER BY value COLLATE NOCASE',args)
    if source!='全部': base+=f' AND {ident(field)} = ?'; args=args+[source]
    _,fi=await query(f"SELECT DISTINCT issue AS value FROM ({base}) WHERE issue != '' ORDER BY value COLLATE NOCASE",args)
    if issue!='全部': base+=' AND issue = ?'; args=args+[issue]
    _,counts=await query(f'SELECT COUNT(*) AS total FROM ({base})',args)
    total=int(counts[0]['total'])
    shelf_view = (module == 'bib' and (tab == '個人書庫' or (tab == '文獻探索' and sub != '期刊論文'))) or (module == 'media' and tab != '搜尋中心' and sub != '網路資源分享卡')
    size = 18 if shelf_view else 30
    page=min(page,max(1,(total+size-1)//size))
    order=f'{ident(sort)} COLLATE NOCASE'
    if sort in ('added','published'): order=f'julianday({ident(sort)})'
    if sort=='rating':
        order="CASE rating "+' '.join(f"WHEN '{v}' THEN {i}" for i,v in enumerate(['S','A','A-','B','B-','C','C-','待讀']))+' ELSE 99 END'
    # Trim only display payloads, after filtering/searching full text in SQL.
    projected=[]
    for k in FIELDS:
        if k in ('notes','summary'): projected.append(f'substr({k},1,1200) AS {k}')
        elif k=='image': projected.append("CASE WHEN length(image)<=30000 THEN image ELSE '' END AS image")
        else: projected.append(ident(k))
    _,items=await query('SELECT '+','.join(projected)+f' FROM ({base}) ORDER BY ({order}) IS NULL, {order} '+('ASC' if asc else 'DESC')+', id ASC LIMIT ? OFFSET ?',args+[size,(page-1)*size])
    return {'items':items,'total':total,'page':page,'page_size':size,
            'sources':[r['value'] for r in fs],'issues':[r['value'] for r in fi],
            'checked_at':int(time.time()),'version':'layout-v4'}


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
    return rows[0]


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
