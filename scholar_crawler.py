import traceback
import aiohttp
import os
import re
import requests
import cloudscraper
import base64
import libsql_client
import urllib.parse
import feedparser
from datetime import datetime
from bs4 import BeautifulSoup
from PIL import Image  # 🌟 新增：用於圖片壓縮
import io              # 🌟 新增：用於記憶體緩衝區

# ==========================================
# 1. 取得環境變數
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")
GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY")  # 🌟 新增：讀取 Google API 金鑰

# ==========================================
# 🛡️ 安全圖片下載器 (支援 Pillow 智慧壓縮與 Base64)
# ==========================================
def get_secure_image_base64(img_url, source=""):
    if not img_url: return ""
    if str(img_url).startswith("data:image"): return img_url
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
        if source == "douban": headers["Referer"] = "https://book.douban.com/"
            
        res = scraper.get(img_url, headers=headers, timeout=10)
        if res.status_code == 200 and len(res.content) > 500:
            # 🌟 圖片瘦身手術同步實裝
            try:
                img = Image.open(io.BytesIO(res.content))
                if img.mode in ("RGBA", "P"): 
                    img = img.convert("RGB")
                img.thumbnail((300, 450)) # 限制最大長寬
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=75, optimize=True)
                compressed_content = buffer.getvalue()
                return f"data:image/jpeg;base64,{base64.b64encode(compressed_content).decode('utf-8')}"
            except Exception as e:
                print(f"圖片壓縮失敗，退回原圖: {e}")
                content_type = res.headers.get('Content-Type', 'image/jpeg')
                return f"data:{content_type};base64,{base64.b64encode(res.content).decode('utf-8')}"
    except: pass
    return img_url

# ==========================================
# 🌟 智慧封面搜尋引擎 (支援語系分流與 Syndetics)
# ==========================================
def get_best_cover(isbn, title, author, publisher):
    headers = {"User-Agent": "Mozilla/5.0"}
    clean_isbn = re.sub(r'[^0-9X]', '', str(isbn).upper()) if isbn else ""

    # --- 1. 日文與華文出版品分流 ---
    if clean_isbn:
        if clean_isbn.startswith("9784") or clean_isbn.startswith("9794"):
            try:
                res = requests.get(f"https://api.openbd.jp/v1/get?isbn={clean_isbn}", timeout=5).json()
                if res and res[0] and res[0].get("summary", {}).get("cover"):
                    return get_secure_image_base64(res[0]["summary"]["cover"], "openbd")
            except: pass
            return get_secure_image_base64(f"https://www.hanmoto.com/bd/img/{clean_isbn}.jpg", "hanmoto")
            
        elif clean_isbn.startswith("9787") or clean_isbn.startswith("978957") or clean_isbn.startswith("978986") or clean_isbn.startswith("978626"):
            try:
                scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
                res = scraper.get(f"https://book.douban.com/isbn/{clean_isbn}/", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    mainpic = soup.find("div", id="mainpic")
                    if mainpic and mainpic.find("img"):
                        return get_secure_image_base64(mainpic.find("img").get("src", "").replace("/s/public/", "/l/public/"), "douban")
            except: pass

    # --- 2. 歐美出版品：Syndetics 優先 ---
    if clean_isbn:
        syndetics_url = f"https://syndetics.com/index.aspx?isbn={clean_isbn}/lc.jpg&client=test"
        try:
            res = requests.get(syndetics_url, headers=headers, timeout=5)
            if res.status_code == 200 and len(res.content) > 100:
                return syndetics_url
        except: pass
    
    # --- 3. MIT Press 專屬 CDN ---
    if publisher == "MIT Press" and clean_isbn:
        img_url = f"https://mit-press-new-us.imgix.net/covers/{clean_isbn}.jpg"
        try:
            if requests.head(img_url, headers=headers, timeout=5).status_code == 200:
                return img_url
        except: pass

    # --- 4. Google Books (精準搜尋與降噪盲搜，同步 403 破解) ---
    google_headers = {"X-Forwarded-For": "168.95.1.1"} # 🌟 台灣 IP 偽裝
    
    if clean_isbn:
        try:
            # 🌟 加入 country=TW
            url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}&country=TW"
            if GOOGLE_BOOKS_API_KEY: url += f"&key={GOOGLE_BOOKS_API_KEY}"
            res = requests.get(url, headers=google_headers, timeout=5).json()
            
            if "items" in res and len(res["items"]) > 0:
                img = res["items"][0].get("volumeInfo", {}).get("imageLinks", {}).get("thumbnail")
                if img: return get_secure_image_base64(img.replace("http://", "https://"), "google")
            else:
                # 🌟 如果嚴格標籤搜不到，啟動寬鬆數字盲搜兜底
                url_loose = f"https://www.googleapis.com/books/v1/volumes?q={clean_isbn}&country=TW"
                if GOOGLE_BOOKS_API_KEY: url_loose += f"&key={GOOGLE_BOOKS_API_KEY}"
                res_loose = requests.get(url_loose, headers=google_headers, timeout=5).json()
                if "items" in res_loose and len(res_loose["items"]) > 0:
                    img = res_loose["items"][0].get("volumeInfo", {}).get("imageLinks", {}).get("thumbnail")
                    if img: return get_secure_image_base64(img.replace("http://", "https://"), "google")
        except: pass

    try:
        short_title = re.sub(r'[^a-zA-Z0-9\s]', '', title.split(':')[0].strip())
        query = urllib.parse.quote(f"{short_title} {author.split(',')[0]}")
        # 🌟 書名盲搜同樣加入 country=TW 與標頭
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&country=TW"
        if GOOGLE_BOOKS_API_KEY: url += f"&key={GOOGLE_BOOKS_API_KEY}"
        res = requests.get(url, headers=google_headers, timeout=5).json()
        if "items" in res and len(res["items"]) > 0:
            img = res["items"][0].get("volumeInfo", {}).get("imageLinks", {}).get("thumbnail")
            if img: return get_secure_image_base64(img.replace("http://", "https://"), "google")
    except: pass

    # --- 5. Open Library (最終備用) ---
    if clean_isbn:
        try:
            if requests.get(f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean_isbn}&format=json", timeout=5).json():
                return f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"
        except: pass

    return ""

# ==========================================
# 3. 爬蟲核心與資料庫寫入
# ==========================================
def fetch_from_crossref(member_id, publisher_name):
    print(f"🔍 [Crossref] 正在擷取 {publisher_name}...")
    url = f"https://api.crossref.org/members/{member_id}/works"
    params = {"filter": "type:book,type:monograph", "sort": "published", "order": "desc", "rows": 30}
    headers = {"User-Agent": "BiblioappCloud/1.0"}
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)
        items = res.json().get("message", {}).get("items", [])
        
        def get_sort_date(item):
            date_obj = item.get("issued") or item.get("published-print") or item.get("published-online") or {}
            parts = date_obj.get("date-parts", [[0]])[0]
            year = parts[0] if len(parts) > 0 and parts[0] else 0
            month = parts[1] if len(parts) > 1 and parts[1] else 1
            return (year, month)

        items.sort(key=get_sort_date, reverse=True)
        
        records = []
        for item in items[:20]:
            title = item.get("title", ["未命名書籍"])[0]
            authors_list = item.get("author", [])
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list]) or publisher_name
            
            date_obj = item.get("issued") or item.get("published-print") or {}
            date_parts = date_obj.get("date-parts", [[]])[0]
            pub_date = f"{date_parts[0]}-{date_parts[1]:02d}" if len(date_parts) >= 2 else str(date_parts[0]) if date_parts else "未知日期"
            
            isbn_list = item.get("ISBN", [])
            isbn_clean = re.sub(r'[^0-9X]', '', str(isbn_list[0])) if isbn_list else ""
            link = item.get("URL", f"https://doi.org/{item.get('DOI', '')}")
            
            image_url = get_best_cover(isbn_clean, title, author, publisher_name)
            
            records.append({
                "type": "Book", "title": title, "author": author, "publisher_journal": publisher_name, "issue_volume": "",
                "identifier": isbn_clean or link, "publish_date": pub_date, "abstract": "（API 擷取資訊）", "link": link, "image": image_url
            })
        return records
    except Exception as e:
        print(f"❌ [{publisher_name}] 擷取失敗: {e}")
        return []

def parse_urbanomic_forthcoming(html, base_url="https://www.urbanomic.com/book/"):
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.select('li.card, a.pubs-feature, article')
    recognized, books = 0, {}
    for card in cards:
        title_tag = card.select_one('.card-title, .pubs-feature-title, h2, h3')
        link_tag = card if card.name == 'a' else card.find('a', href=True)
        if not title_tag or not link_tag:
            continue
        link = urllib.parse.urljoin(base_url, link_tag.get('href', ''))
        parsed = urllib.parse.urlparse(link)
        if parsed.hostname not in {'urbanomic.com', 'www.urbanomic.com'} or not re.match(r'^/book/[^/]+/?$', parsed.path):
            continue
        title = title_tag.get_text(' ', strip=True)
        if not title:
            continue
        recognized += 1
        text = card.get_text(' ', strip=True)
        if not re.search(r'\bFORTHCOMING\b', text, re.I):
            continue
        date = card.select_one('.card-date, .pubs-feature-date')
        author = card.select_one('.card-by, .pubs-feature-by')
        img = card.find('img')
        image_url = (img.get('src') or img.get('data-src') or '') if img else ''
        books[link] = {
            'type': 'Book', 'title': title,
            'author': author.get_text(' ', strip=True) if author else 'Urbanomic',
            'publisher_journal': 'Urbanomic', 'identifier': link, 'link': link,
            'publish_date': date.get_text(' ', strip=True) if date else '即將出版',
            'abstract': '（即將出版之前瞻書目）',
            'image': urllib.parse.urljoin(base_url, image_url) if image_url else '',
            'is_manual': 0, 'category': '學術專著',
        }
    if not recognized:
        raise RuntimeError('Urbanomic: no recognizable book cards; page layout changed or access blocked')
    return list(books.values())


def crawl_urbanomic_forthcoming():
    print("🔍 [Urbanomic] 準備擷取 Forthcoming 書目...", flush=True)
    response = HTTP.get('https://www.urbanomic.com/book/', timeout=(10, 60))
    response.raise_for_status()
    return parse_urbanomic_forthcoming(response.text, response.url)


def crawl_utp():
    print("🔍 [東京大学出版会] 準備擷取新刊清單...")
    url = "https://www.utp.or.jp/search/new.html"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    books = []
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        book_list = soup.find('div', class_='booklist')
        if not book_list:
            return books
            
        items = book_list.find_all('div', class_='item')
        
        for item in items:
            ttl_tag = item.find('div', class_='ttl').find('a')
            title = ttl_tag.get_text(strip=True) if ttl_tag else "未命名書籍"
            raw_link = ttl_tag['href'] if ttl_tag else ""
            link = f"https://www.utp.or.jp{raw_link}" if raw_link else url
            
            author_tag = item.find('div', class_='author')
            author = author_tag.get_text(separator=' ', strip=True) if author_tag else "東京大学出版会"
            
            img_tag = item.find('div', class_='image').find('img')
            image_url = img_tag['src'] if img_tag else ""
            
            pub_type = "Journal" if "UP " in title else "Book"
            
            books.append({
                "type": pub_type,
                "title": title,
                "author": author,
                "publisher_journal": "東京大学出版会",
                "identifier": link, 
                "link": link,
                "publish_date": datetime.utcnow().strftime("%Y-%m"), 
                "abstract": "（東京大学出版会新刊）",
                "image": image_url,
                "is_manual": 0,
                "category": "學術專著"
            })
    except Exception as e:
        print(f"❌ 東京大学出版会 爬取失敗: {e}")
        
    return books
    
def crawl_verso():
    print("🔍 [Verso Books] 準備擷取 Atom...")
    url = "https://www.versobooks.com/collections/catalog.atom"
    feed = feedparser.parse(url)
    books = []
    
    for entry in feed.entries:
        author = entry.author if 'author' in entry else "Verso Books"
        abstract_text = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300]
        
        books.append({
            "type": "Book",
            "title": entry.title,
            "author": author,
            "publisher_journal": "Verso Books",
            "identifier": entry.link, 
            "link": entry.link,
            "publish_date": entry.get("published", datetime.utcnow().strftime("%Y-%m-%d")),
            "abstract": abstract_text,
            "image": "", 
            "is_manual": 0,
            "category": "學術專著"
        })
    return books
    
def crawl_seidosha():
    print("🔍 [青土社] 準備擷取單期目錄...")
    try:
        res = requests.get("https://www.seidosha.co.jp/", timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.find("div", id="new_mag").find_all("div", class_="col-link-items")
        records = []
        
        for item in items:
            a_tag = item.find("a")
            raw_link = a_tag.get("href", "")
            link = f"https://www.seidosha.co.jp{raw_link.lstrip('.')}"
            
            issue_title = item.find("h3", class_="h5").get_text(strip=True)
            img_src = item.find("img").get("src", "")
            image_url = f"https://www.seidosha.co.jp{img_src}"
            
            journal_name = ""
            if "ユリイカ" in issue_title: journal_name = "ユリイカ"
            elif "現代思想" in issue_title: journal_name = "現代思想"
            
            is_journal = bool(journal_name)
            
            if is_journal:
                try:
                    inner_res = requests.get(link, timeout=15)
                    inner_res.encoding = 'utf-8'
                    inner_soup = BeautifulSoup(inner_res.text, "html.parser")
                    
                    info_area = inner_soup.find("div", class_="book-info-text")
                    if info_area:
                        lines = info_area.get_text(separator='\n').split('\n')
                        article_count = 0
                        for line in lines:
                            clean_line = line.strip()
                            
                            if '／' in clean_line:
                                parts = clean_line.split('／')
                                article_title = parts[0].strip()
                                article_author = parts[1].strip() if len(parts) > 1 else "未知作者"
                                
                                article_count += 1
                                records.append({
                                    "type": "Journal",
                                    "title": article_title,
                                    "author": article_author,
                                    "publisher_journal": journal_name, 
                                    "issue_volume": issue_title, 
                                    "identifier": f"{link}_art_{article_count}",
                                    "publish_date": datetime.utcnow().strftime("%Y-%m-%d"),
                                    "abstract": "（青土社單篇論文）",
                                    "link": link,
                                    "image": image_url
                                })
                        if article_count > 0:
                            continue 
                except Exception as e:
                    print(f"⚠️ 青土社目錄擷取失敗，退回整本記錄模式: {e}")

            id_match = re.search(r'id=(\d+)', link)
            identifier = f"seidosha_{id_match.group(1)}" if id_match else link
            records.append({
                "type": "Journal" if is_journal else "Book",
                "title": issue_title, 
                "author": item.find("p", class_="author").get_text(strip=True) or "青土社",
                "publisher_journal": journal_name if is_journal else "青土社", 
                "issue_volume": issue_title if is_journal else "", 
                "identifier": identifier, 
                "publish_date": datetime.utcnow().strftime("%Y-%m-%d"), 
                "abstract": "（青土社新刊）", 
                "link": link, 
                "image": image_url
            })
        return records
    except Exception as e: 
        print(f"❌ [青土社] 錯誤: {e}")
        return []        

# Journal watchlist: 30 requested journals plus 3 existing subscriptions.
# Electronic ISSNs are intentional: some print endpoints only contain archives.
JOURNALS = [
    ('1520-9857', 'MCLC (Modern Chinese Literature and Culture)'),
    ('2578-3491', 'PRISM: Theory and Modern Chinese Literature'),
    ('1673-7318', 'Frontiers of Literary Studies in China'),
    ('2768-3532', 'Chinese literature and thought today'),
    ('2687-8194', 'Literature and Modern China'),
    ('1750-8061', 'Journal of Chinese Cinemas'),
    ('2329-0048', 'Journal of Chinese Literature and Culture'),
    ('1067-9847', 'positions: asia critique'),
    ('1464-9373', 'Inter-Asia Cultural Studies'),
    ('2070-3449', 'China Perspectives'),
    ('1076-0962', 'ISLE: Interdisciplinary Studies in Literature and Environment'),
    ('1080-6520', 'Configurations'),
    ('0091-7729', 'Science Fiction Studies'),
    ('1468-8417', 'Green Letters: Studies in Ecocriticism'),
    ('0014-5483', 'Extrapolation'),
    ('1080-661X', 'New Literary History'),
    ('0093-1896', 'Critical Inquiry'),
    ('1460-2458', 'Cultural Critique'),
    ('0950-2386', 'Cultural Studies'),
    ('0010-4124', 'Comparative Literature'),
    ('2201-1919', 'Environmental Humanities'),
    ('2640-9747', 'Media+Environment'),
    ('1474-4740', 'cultural geographies'),
    ('0263-7758', 'Environment and Planning D: Society and Space'),
    ('2514-8486', 'Environment and Planning E: Nature and Space'),
    ('0309-1325', 'Progress in Human Geography'),
    ('0263-2764', 'Theory, Culture & Society'),
    ('0306-3127', 'Social Studies of Science'),
    ('0162-2439', 'Science, Technology, & Human Values'),
    ('0016-7185', 'Geoforum'),
    ('0190-3659', 'boundary 2'),
    ('2405-6472', 'Journal of World Literature (JWL)'),
    ('0010-4132', 'Comparative Literature Studies (CLS)'),
]

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HTTP = requests.Session()
HTTP.headers['User-Agent'] = 'MonoreaderScholar/2.0 (journal metadata tracking)'
HTTP.mount('https://', HTTPAdapter(max_retries=Retry(
    total=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=['GET'], respect_retry_after_header=True)))


def get_json(url, params=None):
    params = dict(params or {})
    email = os.getenv('CROSSREF_MAILTO', '').strip()
    if email:
        params['mailto'] = email
    time.sleep(1)
    response = HTTP.get(url, params=params, timeout=(10, 60))
    response.raise_for_status()
    return response.json()['message']


def plain(value):
    return BeautifulSoup(str(value or ''), 'html.parser').get_text(' ', strip=True)


def date_parts(item):
    issue_date = (item.get('journal-issue') or {}).get('published-print', {})
    for value in [issue_date] + [item.get(k, {}) for k in
                                 ('published-print', 'issued', 'published', 'published-online')]:
        parts = (value or {}).get('date-parts', [[]])[0]
        if parts and parts[0]:
            return tuple(int(v) for v in parts[:3])
    return ()


def date_string(parts):
    return '-'.join(str(v) if i == 0 else f'{v:02d}' for i, v in enumerate(parts))


def issue_key(item):
    volume = str(item.get('volume') or '').strip()
    issue = str(item.get('issue') or (item.get('journal-issue') or {}).get('issue') or '').strip()
    if issue:
        year = str(date_parts(item)[0]) if date_parts(item) else '未知年份'
        return (volume or year, issue, 'issue' if volume else 'year_issue')
    if volume:
        return (volume, '', 'volume')
    return None


def natural(value):
    return tuple((1, int(v)) if v.isdigit() else (0, v.casefold())
                 for v in re.findall(r'\d+|\D+', value))


def issue_label(key):
    volume, issue, kind = key
    if kind == 'year_issue':
        return f'{volume}, Issue {issue}'
    if issue:
        return f'Vol. {volume}, Issue {issue}'
    return f'Vol. {volume}（未提供期號）'


def collect_crossref(issn, since, max_pages=30):
    """Exhaust the date window; never silently accept truncated pagination."""
    cursor, records = '*', {}
    for _ in range(max_pages):
        message = get_json(f'https://api.crossref.org/journals/{issn}/works', {
            'filter': f'type:journal-article,from-pub-date:{since}',
            'rows': 500, 'cursor': cursor,
        })
        items = message.get('items', [])
        for item in items:
            if item.get('DOI'):
                records[item['DOI'].lower()] = item
        if len(items) < 500:
            return list(records.values())
        cursor = message.get('next-cursor')
        if not cursor:
            raise RuntimeError('Crossref pagination missing next-cursor; scan incomplete')
    raise RuntimeError(f'Crossref exceeded {max_pages} pages; narrow --since or raise --max-pages')


def journal_record(item, journal_name):
    doi = str(item.get('DOI') or '').strip().lower()
    title = plain((item.get('title') or [''])[0])
    if not doi or not title:
        raise ValueError('Crossref article has no DOI or title')
    key = issue_key(item)
    authors = [a.get('name') or ' '.join(filter(None, [a.get('given'), a.get('family')]))
               for a in item.get('author', [])]
    return {
        'type': 'Journal', 'title': title, 'author': ', '.join(filter(None, authors)),
        'publisher_journal': journal_name,
        'issue_volume': issue_label(key) if key else '未編期／Online First',
        'identifier': doi, 'publish_date': date_string(date_parts(item)),
        'abstract': plain(item.get('abstract')), 'link': 'https://doi.org/' + doi,
        'image': '',
    }


def select_journal_records(items, name, issues=3, include_online=True):
    groups = {issue_key(i) for i in items if issue_key(i)}
    ordered = sorted(groups, key=lambda k: (natural(k[0]), natural(k[1])), reverse=True)
    chosen = set(ordered[:issues])
    selected = [i for i in items if issue_key(i) in chosen or
                (include_online and issue_key(i) is None)]
    records = [journal_record(i, name) for i in selected]
    records.sort(key=lambda r: (r['publish_date'], r['identifier']), reverse=True)
    return records, [issue_label(k) for k in ordered[:issues]]


def fetch_journal_from_crossref(issn, journal_name, since=None, issues=3,
                                max_pages=30, include_online=True):
    since = since or f'{datetime.now(timezone.utc).year - 3}-01-01'
    items = collect_crossref(issn, since, max_pages)
    if not items:
        raise RuntimeError(f'Crossref has no articles since {since}; inspect publisher coverage')
    records, labels = select_journal_records(items, journal_name, issues, include_online)
    if not records:
        raise RuntimeError('No numbered issues or online-first articles found')
    print(f'  {journal_name}: {len(records)} articles; ' + ' / '.join(labels))
    return records


def parse_flsc_toc(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    articles = []
    for card in soup.select('.article-list .article-l'):
        anchor, doi, citation = (card.select_one(c) for c in
                                 ('.j-title a[href]', '.j-doi', '.j-volumn'))
        if not anchor or not doi or not citation:
            raise RuntimeError('FLSC TOC metadata missing; page layout may have changed')
        match = re.search(r'(\d{4}),\s*(\d+)\(([^)]+)\)', citation.get_text(' ', strip=True))
        if not match:
            raise RuntimeError('FLSC volume/issue format unrecognised')
        author = card.select_one('.j-author')
        articles.append({
            'type': 'Journal', 'title': plain(anchor.get_text()),
            'author': plain(author.get_text()) if author else '',
            'publisher_journal': 'Frontiers of Literary Studies in China',
            'issue_volume': f'Vol. {match[2]}, Issue {match[3]}',
            'identifier': doi['href'].split('doi.org/')[-1].lower(),
            'publish_date': match[1], 'abstract': '',
            'link': urllib.parse.urljoin(base_url, anchor['href']), 'image': '',
        })
    if not articles:
        raise RuntimeError('FLSC current TOC empty or blocked')
    previous = next((a.get('href') for a in soup.find_all('a', href=True)
                     if a.get_text(strip=True) == 'Previous'), None)
    return articles, urllib.parse.urljoin(base_url, previous) if previous else None


def fetch_flsc_current(issues=3):
    url, records = 'https://journal.hep.com.cn/flsc/EN/current', {}
    for _ in range(issues):
        response = HTTP.get(url, timeout=(10, 60))
        response.raise_for_status()
        articles, previous = parse_flsc_toc(response.text, response.url)
        for item in articles:
            time.sleep(0.5)
            detail = HTTP.get(item['link'], timeout=(10, 60))
            detail.raise_for_status()
            soup = BeautifulSoup(detail.text, 'html.parser')
            def value(name):
                meta = soup.find('meta', attrs={'name':name})
                return meta.get('content','') if meta else ''
            if value('citation_doi').lower() != item['identifier']:
                raise RuntimeError('FLSC article DOI does not match TOC')
            # TOC had repeated unrelated abstracts: use individual article metadata.
            item['abstract'] = plain(value('citation_abstract'))
            item['publish_date'] = value('citation_publication_date').replace('/','-') or item['publish_date']
            records[item['identifier']] = item
        if not previous:
            break
        if urllib.parse.urlparse(previous).netloc != 'journal.hep.com.cn':
            raise RuntimeError('FLSC previous-issue link points outside publisher')
        url = previous
    return list(records.values())


def safe_error(text):
    for secret in (TURSO_DATABASE_URL, TURSO_TOKEN, GOOGLE_BOOKS_API_KEY):
        if secret:
            text = text.replace(secret, '[REDACTED]')
    return text


class RetryingDatabase:
    """Retry only transport failures; callers must use idempotent SQL.

    Three retries after the initial attempt. Never retry SQL/schema/auth errors.
    A new client is created after each failed transport, including lost replies.
    """
    def __init__(self):
        self.client = None
        self.retries = 0

    def close(self):
        client, self.client = self.client, None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass  # Cleanup must not hide the original failure or lose report.

    def _call(self, method, *args):
        for attempt in range(4):
            try:
                if self.client is None:
                    self.client = libsql_client.create_client_sync(
                        url=TURSO_DATABASE_URL, auth_token=TURSO_TOKEN)
                return getattr(self.client, method)(*args)
            except (aiohttp.ClientConnectionError, TimeoutError, ConnectionError):
                self.close()
                if attempt == 3:
                    raise
                self.retries += 1
                delay = 2 ** (attempt + 1)
                print(f'Database transport failure: reconnecting, retry {attempt + 1}/3 in {delay}s', flush=True)
                time.sleep(delay)

    def execute(self, *args):
        return self._call('execute', *args)

    def batch(self, statements):
        return self._call('batch', statements)


def check_schema(client):
    columns = {row[1] for row in client.execute('PRAGMA table_info(academic_pubs)').rows}
    required = {'type','title','author','publisher_journal','issue_volume','identifier',
                'publish_date','abstract','link','image','category','book_status'}
    if required - columns:
        raise RuntimeError('academic_pubs missing columns: ' + ', '.join(sorted(required - columns)))
    health_cols = {row[1] for row in client.execute('PRAGMA table_info(crawler_health)').rows}
    return columns, {'source_name','status','last_check','error_msg'} <= health_cols


def save_to_db(items, client=None, columns=None):
    owned = client is None
    if owned:
        client = RetryingDatabase()
    try:
        columns = columns or check_schema(client)[0]
        manual_guard = ' WHERE COALESCE(academic_pubs.is_manual, 0) = 0' if 'is_manual' in columns else ''
        sql = '''INSERT INTO academic_pubs
            (type,title,author,publisher_journal,issue_volume,identifier,publish_date,abstract,link,image,category,book_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,0)
            ON CONFLICT(identifier) DO UPDATE SET
              title=excluded.title,
              author=COALESCE(NULLIF(excluded.author,''),academic_pubs.author),
              issue_volume=CASE WHEN excluded.issue_volume IN ('','未編期／Online First')
                 AND COALESCE(academic_pubs.issue_volume,'') NOT IN ('','未編期／Online First')
                 THEN academic_pubs.issue_volume ELSE excluded.issue_volume END,
              publish_date=COALESCE(NULLIF(excluded.publish_date,''),academic_pubs.publish_date),
              abstract=COALESCE(NULLIF(excluded.abstract,''),academic_pubs.abstract),
              link=COALESCE(NULLIF(excluded.link,''),academic_pubs.link),
              image=COALESCE(NULLIF(excluded.image,''),academic_pubs.image)
        ''' + manual_guard
        statements = []
        for item in items:
            if not item.get('identifier') or not item.get('title'):
                raise ValueError('Refusing record without identifier or title')
            values = [item.get(k, '') or '' for k in ('type','title','author','publisher_journal',
                      'issue_volume','identifier','publish_date','abstract','link','image')]
            statements.append((sql, values + [item.get('category') or '未分類']))
        if statements:
            client.batch(statements)
    finally:
        if owned:
            client.close()


def update_health(client, name, status, message):
    now = datetime.now(timezone.utc).isoformat()
    client.execute('''INSERT INTO crawler_health(source_name,status,last_check,error_msg)
        VALUES (?,?,?,?) ON CONFLICT(source_name) DO UPDATE SET
        status=excluded.status,
        last_check=CASE WHEN excluded.status='OK' THEN excluded.last_check
            ELSE COALESCE(NULLIF(crawler_health.last_check,''),excluded.last_check) END,
        error_msg=excluded.error_msg''', [name, status, now, message[:1500]])


def main(argv=None):
    parser = argparse.ArgumentParser(description='Monoreader books and journal issue tracker')
    parser.add_argument('--dry-run', action='store_true', help='Fetch without connecting to Turso')
    parser.add_argument('--journals-only', action='store_true')
    parser.add_argument('--journal', action='append', default=[], help='ISSN or exact name; repeatable')
    parser.add_argument('--since', default=f'{datetime.now(timezone.utc).year - 3}-01-01')
    parser.add_argument('--issues', type=int, default=3)
    parser.add_argument('--max-pages', type=int, default=30)
    parser.add_argument('--no-online-first', action='store_true')
    parser.add_argument('--report', default='scholar-crawl-report.json')
    args = parser.parse_args(argv)
    datetime.strptime(args.since, '%Y-%m-%d')
    if args.issues < 1 or args.max_pages < 1:
        parser.error('--issues and --max-pages must be positive')
    known = {s for pair in JOURNALS for s in pair}
    if set(args.journal) - known:
        parser.error('Unknown --journal: ' + ', '.join(set(args.journal) - known))
    client, columns, health = None, None, False
    if not args.dry_run:
        if not TURSO_DATABASE_URL or (not TURSO_DATABASE_URL.startswith('file:') and not TURSO_TOKEN):
            parser.error('Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN (or TURSO_TOKEN)')
        client = RetryingDatabase()
        try:
            columns, health = check_schema(client)
        except Exception:
            client.close()
            raise
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'dry_run': args.dry_run,
              'since': args.since, 'sources': []}
    sources = []
    if not args.journals_only and not args.journal:
        sources.extend([
            ('MIT Press', lambda: fetch_from_crossref('281', 'MIT Press')),
            ('Duke University Press', lambda: fetch_from_crossref('73', 'Duke University Press')),
            ('東京大学出版会', crawl_utp), ('Verso Books', crawl_verso),
            ('Urbanomic', crawl_urbanomic_forthcoming), ('青土社', crawl_seidosha),
        ])
    for issn, name in JOURNALS:
        if args.journal and issn not in args.journal and name not in args.journal:
            continue
        if name == 'Frontiers of Literary Studies in China':
            sources.append((name, lambda: fetch_flsc_current(args.issues)))
        else:
            sources.append((name, lambda issn=issn, name=name: fetch_journal_from_crossref(
                issn, name, args.since, args.issues, args.max_pages, not args.no_online_first)))
    try:
        for name, fetch in sources:
            entry = {'source': name, 'status': 'OK', 'count': 0, 'fetched_count': 0,
                     'write_status': 'not_attempted', 'stage': 'fetch_parse'}
            retries_before = client.retries if client else 0
            try:
                records = fetch()
                entry['fetched_count'] = len(records)
                if not records and name != 'Urbanomic':
                    raise RuntimeError('Source returned no records; inspect source/API availability')
                if not records:
                    entry['message'] = 'No forthcoming books; book page structure validated'
                if client and records:
                    entry.update(stage='database_write', write_status='pending')
                    save_to_db(records, client, columns)
                    entry['write_status'] = 'success'
                elif args.dry_run:
                    entry['write_status'] = 'dry_run'
                entry['stage'] = 'complete'
                entry.update(count=len(records), issues=sorted({r.get('issue_volume','') for r in records}),
                             newest_publication=max((r.get('publish_date','') for r in records), default=''))
            except Exception as exc:
                entry.update(status='ERROR', error=safe_error(f'{type(exc).__name__}: {exc}'))
                if entry['write_status'] == 'pending':
                    entry['write_status'] = 'unconfirmed'
                print(safe_error(traceback.format_exc()), file=sys.stderr)
                print(f'::error title=Scholar crawler::{name}: {type(exc).__name__}', file=sys.stderr)
            if client and health:
                try:
                    update_health(client, name, entry['status'], entry.get('error', ''))
                except Exception as exc:
                    entry.update(status='ERROR', health_error=safe_error(f'{type(exc).__name__}: {exc}'))
                    print(safe_error(traceback.format_exc()), file=sys.stderr)
            entry['database_retries'] = (client.retries if client else 0) - retries_before
            report['sources'].append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
    finally:
        if client:
            client.close()
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return int(any(e['status'] != 'OK' for e in report['sources']))


if __name__ == '__main__':
    sys.exit(main())
