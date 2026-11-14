"""Monoreader connection milestone. Authenticated SELECT-only service."""
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
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


LOGIN = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Monoreader 登入</title><style>body{background:#f5f3ed;color:#233e38;font:16px/1.7 system-ui;display:grid;place-items:center;min-height:90vh;margin:20px}main{max-width:380px;width:100%}h1{font-family:Georgia,serif;font-size:40px}input,button{box-sizing:border-box;width:100%;padding:14px;font:inherit;margin:10px 0;border:1px solid #c5cec1;border-radius:8px}button{background:#233e38;color:white}p{color:#657268;font-size:14px}</style><main><h1>monoreader</h1><p>真實資料連線測試 · 唯讀版本</p><form method="post" action="/login"><label for="password">你設定的 App 登入密碼</label><input id="password" type="password" name="password" required autocomplete="current-password" maxlength="512"><button>登入</button></form><p>密碼是在 Vercel 的 APP_PASSWORD 設定，不是 GitHub 或 Turso 密碼。</p></main></html>'''


@app.get('/health')
def health():
    return {'status': 'running', 'mode': 'read-only'}


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
    return (ROOT / 'index.html').read_text(encoding='utf-8')


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


async def query(sql):
    # There is no user-supplied SQL route. Guard every internal statement as well.
    if not sql.lstrip().upper().startswith('SELECT ') or ';' in sql:
        raise RuntimeError('Only SELECT is permitted')
    url, token = endpoint()
    try:
        async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
            res = await client.post(url, headers={'Authorization': 'Bearer ' + token}, json={'requests': [{'type': 'execute', 'stmt': {'sql': sql, 'want_rows': True}}, {'type': 'close'}]})
        if res.status_code in (401, 403):
            raise HTTPException(502, 'Turso 拒絕連線，請核對 URL 與 Token 是否屬於同一個資料庫。')
        if res.status_code != 200:
            raise HTTPException(502, 'Turso 連線失敗（HTTP ' + str(res.status_code) + '）。')
        return decode_result(res.json())
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, 'Turso 暫時無法讀取或回應格式不符；請稍後重新載入。') from None


@app.get('/api/table/{table}')
async def read_table(table: str, request: Request, offset: int = 0):
    require_login(request)
    if table not in TABLES or offset < 0 or offset > 450 or offset % 50:
        raise HTTPException(400, '不支援的資料表或頁數。')
    _, existing = await query("SELECT name FROM sqlite_master WHERE type='table'")
    if table not in [r['name'] for r in existing]:
        return {'table': table, 'rows': [], 'total': 0, 'missing': True, 'next_offset': None}
    cols, _ = await query(f'SELECT * FROM "{table}" LIMIT 0')
    lower = {c.lower(): c for c in cols}
    def ident(c):
        return '"' + c.replace('"', '""') + '"'
    ordering = [lower[c.lower()] for c in TABLES[table] if c.lower() in lower][:1]
    for candidate in ('id', 'link', 'identifier', 'url'):
        if candidate in lower and lower[candidate] not in ordering:
            ordering.append(lower[candidate]); break
    order_sql = ' ORDER BY ' + ', '.join(ident(c) + ' DESC' for c in ordering) if ordering else ''
    _, count = await query(f'SELECT COUNT(*) AS total FROM "{table}"')
    _, rows = await query(f'SELECT * FROM "{table}"{order_sql} LIMIT 50 OFFSET {offset}')
    total = int(count[0]['total'])
    end = offset + len(rows)
    return {'table': table, 'rows': rows, 'total': total, 'missing': False, 'truncated': total > 500, 'next_offset': end if len(rows) == 50 and end < min(total, 500) else None}
