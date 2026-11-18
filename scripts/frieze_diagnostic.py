"""Read-only FRIEZE diagnostic. No crawler imports, database access or credentials."""
import json
import os
import platform
import re
import sys
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HOSTS = ('www.frieze.com', 'app.frieze.com')
INDEX = '/magazines/frieze-magazine'
OUTPUT = Path('frieze-diagnostic-results')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language': 'en-GB,en;q=0.9'}
SAFE_HEADERS = {'server', 'content-type', 'cf-ray', 'cf-mitigated', 'x-cache', 'via', 'retry-after', 'x-sucuri-block', 'x-sucuri-id'}


def inspect_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    issues = []
    for a in soup.select('a[href]'):
        u = urlparse(a['href'])
        if u.netloc and u.netloc not in HOSTS:
            continue
        m = re.fullmatch(r'/magazines/frieze-magazine/issue-(\d+)/?', u.path)
        if m:
            issues.append(int(m.group(1)))
    article_links = {urlparse(a['href']).path for a in soup.select('.search-result-container .teaser-title a[href]') if urlparse(a['href']).path.startswith('/article/')}
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    for tag in soup.select('script,style,noscript,input,textarea'):
        tag.decompose()
    visible = soup.get_text(' ', strip=True)
    markers = [x for x in ('access denied', 'just a moment', 'verify you are human', 'captcha', 'request blocked', 'cloudflare', 'akamai', 'incapsula', 'imperva') if x in visible.lower()]
    # Redact IPs and email addresses sometimes printed by denial pages.
    excerpt = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '[IP]', visible[:1200])
    excerpt = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email]', excerpt)
    return {'title': title[:200], 'latest_issue': max(issues) if issues else None,
            'issue_link_count': len(set(issues)), 'article_count': len(article_links),
            'denial_markers': markers, 'text_excerpt': excerpt}


def record(method, host, stage, url, status=None, headers=None, html='', error=None):
    info = inspect_html(html)
    expected = info['issue_link_count'] if stage == 'index' else info['article_count']
    row = dict(method=method, host=host, stage=stage, final_url=url.split('?')[0],
               status=status, headers={k.lower(): v for k, v in (headers or {}).items() if k.lower() in SAFE_HEADERS},
               error=error, content_recognized=bool(expected), **info)
    row['usable'] = bool(status and 200 <= status < 300 and expected and not error)
    return row


def http_probe(host):
    rows = []
    with requests.Session() as session:
        path = INDEX
        for stage in ('index', 'issue'):
            url = 'https://' + host + path
            try:
                r = session.get(url, headers=HEADERS, timeout=(10, 25))
                row = record('requests', host, stage, r.url, r.status_code, r.headers, r.text)
            except requests.RequestException as exc:
                row = record('requests', host, stage, url, error=str(exc)[:500])
            rows.append(row)
            if stage == 'index':
                if not row['usable']:
                    break
                path = INDEX + '/issue-' + str(row['latest_issue'])
    return rows


def browser_probe(host, browser):
    rows = []
    with browser.new_context(locale='en-GB') as context:
        page = context.new_page()
        page.set_default_timeout(10000)
        path = INDEX
        for stage in ('index', 'issue'):
            url = 'https://' + host + path
            navigation = []
            def capture(response):
                if response.request.is_navigation_request() and response.frame == page.main_frame:
                    navigation.append(response)
            page.on('response', capture)
            error = None
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=35000)
                selector = 'a[href*="/magazines/frieze-magazine/issue-"]' if stage == 'index' else '.search-result-container .teaser-title a[href*="/article/"]'
                # Allow normal page JavaScript to finish; never interact with a CAPTCHA.
                try:
                    page.locator(selector).first.wait_for(state='attached', timeout=10000)
                except Exception:
                    pass
            except Exception as exc:
                error = str(exc)[:500]
            try:
                last = navigation[-1] if navigation else None
                row = record('chromium', host, stage, page.url,
                             last.status if last else None,
                             last.all_headers() if last else {}, page.content(), error)
                row['navigation_statuses'] = [r.status for r in navigation]
            except Exception as exc:
                row = record('chromium', host, stage, url, error=str(exc)[:500])
            page.remove_listener('response', capture)
            rows.append(row)
            if stage == 'index':
                if not row['usable']:
                    break
                path = INDEX + '/issue-' + str(row['latest_issue'])
    return rows


def summarize(report):
    lines = ['# FRIEZE 診斷結果', '', '此診斷沒有連線或寫入 Turso。綠色完成只表示診斷已執行，不表示 FRIEZE 已修好。', '',
             '| 方法 | 入口 | 頁面 | HTTP | 可用期刊內容 | 期號／文章數 |', '|---|---|---|---|---|---|']
    for r in report['results']:
        count = r['latest_issue'] if r['stage'] == 'index' else r['article_count']
        lines.append(f"| {r['method']} | {r['host']} | {r['stage']} | {r['status']} | {'是' if r['usable'] else '否'} | {count} |")
    if report.get('browser_error'):
        lines += ['', '瀏覽器測試未能完成：' + report['browser_error'].replace('\n', ' ')[:500]]
    lines += ['', '請下載本次執行的 frieze-diagnostic-results artifact，將 report.json 傳回。',
              '兩種方法均失敗不能單憑此結果確定是 IP 封鎖；還需參照 headers、拒絕摘要及瀏覽器錯誤。']
    return '\n'.join(lines) + '\n'


def main():
    OUTPUT.mkdir(exist_ok=True)
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(), 'platform': platform.platform(), 'packages': {}, 'results': []}
    for name in ('requests', 'beautifulsoup4', 'playwright'):
        try: report['packages'][name] = version(name)
        except PackageNotFoundError: report['packages'][name] = 'not installed'
    for host in HOSTS:
        print('Testing requests:', host, flush=True)
        report['results'].extend(http_probe(host))
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            with pw.chromium.launch(headless=True) as browser:
                report['browser_version'] = browser.version
                for host in HOSTS:
                    print('Testing Chromium:', host, flush=True)
                    try: report['results'].extend(browser_probe(host, browser))
                    except Exception as exc: report['results'].append(record('chromium', host, 'index', 'https://' + host + INDEX, error=str(exc)[:500]))
    except Exception as exc:
        report['browser_error'] = str(exc)[:1000]
    (OUTPUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = summarize(report)
    (OUTPUT / 'summary.md').write_text(summary, encoding='utf-8')
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        with open(summary_path, 'a', encoding='utf-8') as f: f.write(summary)
    print(summary)
    print('Saved:', OUTPUT / 'report.json')


if __name__ == '__main__':
    main()
