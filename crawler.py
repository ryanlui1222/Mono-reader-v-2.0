import feedparser
import pandas as pd
from bs4 import BeautifulSoup
import concurrent.futures
import cloudscraper
import urllib.parse
import re
import json
import requests
import os
import libsql_client
from datetime import datetime

# ==========================================
# 全局網路引擎 & 基礎設定
# ==========================================
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
TIMEOUT = 15

# ==========================================
# 🛠️ 輔助函數 (Helpers)
# ==========================================
def get_soup(url, custom_headers=HEADERS):
    """通用的 HTML 獲取與解析器"""
    try:
        res = scraper.get(url, headers=custom_headers, timeout=TIMEOUT)
        return BeautifulSoup(res.text, 'html.parser') if res.status_code == 200 else None
    except:
        return None

def format_summary(text, author="", max_len=None):
    """通用的摘要清洗器"""
    if not text: return "（無提供文字摘要）"
    text = " ".join(text.split())
    if not max_len:
        eng_count = sum(1 for c in text[:50] if c.isalpha() and c.isascii())
        max_len = 600 if eng_count > 25 else 200 
    summary = text[:max_len] + '...' if len(text) > max_len else text
    return f"**👤 著者：** {author}\n\n{summary}" if author else summary

# ==========================================
# ☁️ Turso 雲端資料庫同步模組
# ==========================================
def get_db_client():
    """獲取 Turso 連線實體"""
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token: return None
    return libsql_client.create_client_sync(url=url, auth_token=token)

# ==========================================
# 🕷️ 各平台專屬爬蟲模組
# ==========================================
def fetch_rss(feed_url, source_name, limit=20, deep_fetch=False):
    articles = []
    try:
        response = scraper.get(feed_url, timeout=TIMEOUT)
        parsed = feedparser.parse(response.content)
        
        def process_entry(entry):
            raw_date = entry.get('published') or entry.get('pubDate') or entry.get('updated') or "最新"
            author = entry.get('author') or entry.get('author_detail', {}).get('name') or ""
            
            raw_text = entry.content[0].value if 'content' in entry else entry.get('summary', '')
            soup = BeautifulSoup(raw_text, 'html.parser')
            img_tag = soup.find('img')
            img_url = urllib.parse.urljoin(entry.link, img_tag['src']) if img_tag and 'src' in img_tag.attrs else None
            text = soup.get_text(separator=" ", strip=True)
            
            if deep_fetch:
                art_soup = get_soup(entry.link)
                if art_soup:
                    if not img_url:
                        og_img = art_soup.find('meta', attrs={'property': 'og:image'})
                        img_url = og_img['content'] if og_img else None
                    
                    if not author:
                        author_meta = art_soup.find('meta', attrs={'name': 'author'}) or art_soup.find('meta', property='og:article:author')
                        if author_meta: author = author_meta['content']
                        
                    paragraphs = [p.get_text(strip=True) for p in art_soup.find_all('p') if len(p.get_text(strip=True)) > 60]
                    clean_p = [p for p in paragraphs if not any(bad in p.lower() for bad in ["subscribe", "newsletter", "sign up"])]
                    if clean_p: text = " ".join(clean_p[:3])
            
            return {
                "Source": source_name, "Title": entry.title, "Link": entry.link,
                "Published": raw_date, 
                "Summary": format_summary(text, author), "Image": img_url
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            articles = [res for res in ex.map(process_entry, parsed.entries[:limit]) if res]
    except Exception as e: print(f"{source_name} 錯誤: {e}")
    return articles

def fetch_thepoint():
    articles = []
    try:
        soup = get_soup("https://thepointmag.com/magazine/")
        if not soup: return articles
        latest_section = soup.find('div', class_='section-top')
        if not latest_section: return articles
        issue_tag = latest_section.find('h1')
        issue_num = issue_tag.get_text(strip=True) if issue_tag else "最新刊"
        source_name = f"The Point ({issue_num})"
        pattern = re.compile(r'https://thepointmag\.com/(examined-life|politics|criticism|dialogue|letter|correspondence)/([^/]+)/?$')
        links = []
        for a in latest_section.find_all('a', href=True):
            href = a['href']
            if pattern.match(href) and href not in links: links.append(href)
        
        def process_link(url):
            art_soup = get_soup(url)
            if not art_soup: return None
            og_title = art_soup.find('meta', property='og:title')
            title = og_title['content'].split('|')[0].strip() if og_title else art_soup.find('h1').get_text(strip=True)
            author_a = art_soup.find('a', href=re.compile(r'/author/'))
            author = author_a.get_text(strip=True) if author_a else ""
            og_img = art_soup.find('meta', property='og:image')
            text = " ".join([p.get_text(strip=True) for p in art_soup.find_all('p') if len(p.get_text(strip=True)) > 80])
            return {"Source": source_name, "Title": title, "Link": url, "Published": issue_num, 
                    "Summary": format_summary(text, author), "Image": og_img['content'] if og_img else None}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            articles = [res for res in ex.map(process_link, links) if res]
    except Exception as e: print(f"The Point 錯誤: {e}")
    return articles

def fetch_eflux():
    try:
        soup = get_soup("https://www.e-flux.com/journal/")
        issues = sorted([a['href'] for a in soup.find_all('a', href=re.compile(r'^/journal/\d+$')) if soup], key=lambda x: int(x.split('/')[-1]), reverse=True)
        if not issues: return []
        issue_num = issues[0].split('/')[-1]
        issue_soup = get_soup(f"https://www.e-flux.com{issues[0]}")
        articles = []
        for card in issue_soup.find_all('div', class_='preview-journalarticle'):
            title_tag = card.find('a', class_='preview-journalarticle__title')
            if not title_tag: continue
            author = card.find('div', class_='preview-journalarticle__author')
            text_tag = card.find('div', class_='preview-journalarticle__text')
            summary = " ".join(re.findall(r'<p[^>]*>(.*?)</p>', str(text_tag))) if text_tag and '<p' in str(text_tag) else (text_tag.get_text(" ", strip=True) if text_tag else "")
            if any(bad in summary.lower() for bad in ["subscribe", "education announces"]): continue
            img = card.find('img')
            articles.append({"Source": f"e-flux Journal (Issue {issue_num})", "Title": title_tag.get_text(strip=True), "Link": f"https://www.e-flux.com{title_tag['href']}", "Published": f"Issue {issue_num}", "Summary": format_summary(summary or "（請點擊標題閱讀原文）", author.get_text(strip=True) if author else ""), "Image": img['src'] if img and 'src' in img.attrs else None})
        return articles
    except Exception as e: print(f"e-flux 錯誤: {e}"); return []

def fetch_eurozine():
    try:
        soup = get_soup("https://www.eurozine.com/essays/")
        articles = []
        for article in soup.find_all('article', class_='p1 col')[:15] if soup else []:
            a_tag = article.find('h3').find('a')
            if not a_tag: continue
            aside = article.find('aside')
            author = "、".join([a.get_text(strip=True) for a in aside.select('ul.color-red a')]) if aside else ""
            time_tag = aside.find('time') if aside else None
            copy_div = article.find('div', class_='copy')
            img = article.find('img')
            articles.append({"Source": "Eurozine", "Title": a_tag.get_text(strip=True), "Link": a_tag['href'], "Published": time_tag.get('datetime', time_tag.get_text(strip=True)) if time_tag else "最新", "Summary": format_summary(copy_div.get_text(" ", strip=True) if copy_div else "（無摘要）", author), "Image": img['src'] if img and 'src' in img.attrs else None})
        return articles
    except Exception as e: print(f"Eurozine 錯誤: {e}"); return []

def fetch_bijutsutecho():
    try:
        soup = get_soup("https://bijutsutecho.com/magazine/series")
        articles = []
        for article in soup.find_all('article', class_='MagazinePageListItem')[:15] if soup else []:
            a_tag = article.find('h2', class_='title').find('a')
            if not a_tag: continue
            title = f"🔒 {a_tag.get_text(strip=True)}" if article.find('div', class_='premium-label') else a_tag.get_text(strip=True)
            lead = article.find('p', class_='lead')
            time_tag = article.find('time')
            img = article.find('img')
            articles.append({"Source": "美術手帖", "Title": title, "Link": urllib.parse.urljoin("https://bijutsutecho.com", a_tag['href']), "Published": time_tag['datetime'] if time_tag else "最新", "Summary": format_summary(lead.get_text(" ", strip=True) if lead else ""), "Image": img['src'] if img and 'src' in img.attrs else None})
        return articles
    except Exception as e: print(f"美術手帖 錯誤: {e}"); return []

def fetch_thepaper():
    try:
        iphone_headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15'}
        res = scraper.get("https://m.thepaper.cn/list_25483", headers=iphone_headers, timeout=TIMEOUT)
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', res.text, re.DOTALL)
        if not match: return []
        items = json.loads(match.group(1)).get('props', {}).get('pageProps', {}).get('data', {}).get('list', [])
        return [{"Source": "澎湃思想市場", "Title": item.get('name', ''), "Link": f"https://www.thepaper.cn/newsDetail_forward_{item.get('contId')}", "Published": item.get('pubTimeNew', '最新'), "Summary": f"**🏷️ 探討議題：** {'、'.join([t.get('tag', '') for t in item.get('tagList', [])]) or '無'}\n\n（點擊標題閱讀原文）", "Image": item.get('pic', '')} for item in items[:15] if item.get('name') and item.get('contId')]
    except Exception as e: print(f"澎湃 錯誤: {e}"); return []

def fetch_webgenron():
    try:
        soup = get_soup("https://webgenron.com/")
        articles, seen = [], set()
        for a in soup.find_all('a', href=True) if soup else []:
            href = a['href']
            if '/articles/' in href and not href.endswith(('/articles', '/articles/')) and href not in seen:
                title = a.get_text(strip=True)
                if len(title) < 8: continue
                seen.add(href)
                full_link = f"https://webgenron.com{href}" if href.startswith('/') else href
                art_soup = get_soup(full_link)
                desc = art_soup.find('meta', attrs={'name': 'description'}) or art_soup.find('meta', property='og:description') if art_soup else None
                articles.append({"Source": "webゲンロン", "Title": title, "Link": full_link, "Published": "最新", "Summary": format_summary(desc['content'] if desc else ""), "Image": None})
                if len(articles) >= 15: break
        return articles
    except Exception as e: print(f"webゲンロン 錯誤: {e}"); return []

def fetch_funambulist():
    try:
        soup = get_soup("https://thefunambulist.net/magazine/issues")
        invalid = ['geo-index', 'stockists', 'subscribe', 'shop', 'podcast', 'editorials', 'network']
        latest_url = next((href if href.startswith('http') else f"https://thefunambulist.net{href}" for a in soup.find_all('a', href=True) if '/magazine/' in (href := a['href']) and not any(b in href for b in invalid) and not href.rstrip('/').endswith(('magazine', 'issues'))), None) if soup else None
        if not latest_url: return []
        issue_soup = get_soup(latest_url)
        issue_title = issue_soup.find('h1').get_text(strip=True) if issue_soup and issue_soup.find('h1') else "最新刊"
        valid_links, seen = [], set()
        is_in_target_section = False 
        for element in issue_soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'a']):
            if element.name.startswith('h'):
                header_text = element.get_text(strip=True).upper()
                if "FEATURED IN THIS ISSUE" in header_text or "NEWS FROM THE FRONT" in header_text: is_in_target_section = True
                elif any(stop_word in header_text for stop_word in ["CONTRIBUTORS", "ISSUE PREVIEW", "SHARE THIS", "PODCAST"]): is_in_target_section = False
            elif element.name == 'a' and is_in_target_section:
                href = element.get('href', '')
                title = element.get_text(strip=True)
                if href.startswith('https://thefunambulist.net/') and len(title) > 8:
                    if title.lower() != "the funambulist" and title not in seen:
                        valid_links.append((title, href)); seen.add(title)
        def process_link(data):
            title, href = data
            art_soup = get_soup(href)
            paragraphs = [p.get_text(strip=True) for p in art_soup.find_all('p') if len(p.get_text(strip=True)) > 80] if art_soup else []
            return {"Source": f"The Funambulist ({issue_title})", "Title": title, "Link": href, "Published": issue_title, "Summary": format_summary(" ".join(paragraphs)), "Image": None}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            return [res for res in ex.map(process_link, valid_links) if res]
    except Exception as e: print(f"Funambulist 錯誤: {e}"); return []

def fetch_mit_reader():
    try:
        data = requests.get("https://api.rss2json.com/v1/api.json?rss_url=https://thereader.mitpress.mit.edu/feed/", timeout=TIMEOUT).json()
        if data.get('status') != 'ok': return []
        articles = []
        for item in data.get('items', [])[:15]:
            soup = BeautifulSoup(item.get('description', ''), 'html.parser')
            img_tag = soup.find('img')
            articles.append({"Source": "MIT Press Reader", "Title": item.get('title', ''), "Link": item.get('link', ''), "Published": item.get('pubDate', '最新'), "Summary": format_summary(soup.get_text(" ", strip=True), item.get('author', '')), "Image": item.get('thumbnail') or (img_tag['src'] if img_tag and 'src' in img_tag.attrs else None)})
        return articles
    except Exception as e: print(f"MIT Press 錯誤: {e}"); return []

def fetch_verse():
    articles = []
    try:
        soup = get_soup("https://www.verse.com.tw/")
        if not soup: return articles
        seen = set()
        valid_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            full_url = urllib.parse.urljoin("https://www.verse.com.tw/", href)
            if '/article/' in href and full_url not in seen:
                seen.add(full_url)
                title = a.get_text(strip=True)
                if not title:
                    img = a.find('img')
                    title = img.get('alt', '') if img else ""
                if len(title) > 5:
                    valid_links.append((title, full_url))
        valid_links = valid_links[:15]
        def process_link(data):
            title, url = data
            art_soup = get_soup(url)
            if not art_soup: return None
            og_img = art_soup.find('meta', property='og:image')
            img_url = og_img['content'] if og_img else None
            author_meta = art_soup.find('meta', attrs={'name': 'author'})
            author = author_meta['content'] if author_meta and author_meta.get('content') else ""
            if author.upper() == "VERSE": author = ""
            og_desc = art_soup.find('meta', property='og:description')
            summary = og_desc['content'] if og_desc and og_desc.get('content') else ""
            if not summary or len(summary) < 20:
                paragraphs = [p.get_text(strip=True) for p in art_soup.find_all('p') if len(p.get_text(strip=True)) > 40]
                summary = " ".join(paragraphs[:3]) if paragraphs else "（請點擊標題閱讀原文）"
            time_tag = art_soup.find('time')
            published = time_tag.get('datetime', '最新') if time_tag else "最新"
            return {"Source": "VERSE", "Title": title, "Link": url, "Published": published, "Summary": format_summary(summary, author), "Image": img_url}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            articles = [res for res in ex.map(process_link, valid_links) if res]
    except Exception as e: print(f"VERSE 錯誤: {e}")
    return articles

def fetch_jiemian():
    articles = []
    try:
        iphone_headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15'}
        soup = get_soup("https://m.jiemian.com/lists/130_1.html", custom_headers=iphone_headers)
        if not soup: return articles
        items = soup.find_all('div', class_='news-view')
        for item in items[:15]:
            title_tag = item.select_one('.news-header h3 a')
            if not title_tag: continue
            title = title_tag.get_text(strip=True)
            link = title_tag['href']
            if link.startswith('/'): link = f"https://m.jiemian.com{link}"
            img_tag = item.select_one('.news-img img')
            img_url = img_tag['src'] if img_tag and 'src' in img_tag.attrs else None
            footer_spans = item.select('.news-footer p span')
            tag = footer_spans[0].get_text(strip=True) if len(footer_spans) > 0 else ""
            pub_date = footer_spans[1].get_text(strip=True) if len(footer_spans) > 1 else "最新"
            summary = f"**🏷️ 探討領域：** {tag}\n\n（請點擊標題閱讀原文）" if tag else "（請點擊標題閱讀原文）"
            articles.append({"Source": "界面文化", "Title": title, "Link": link, "Published": pub_date, "Summary": format_summary(summary), "Image": img_url})
    except Exception as e: print(f"界面文化 錯誤: {e}")
    return articles

def fetch_cinra():
    articles = []
    try:
        soup = get_soup("https://www.cinra.net/")
        if not soup: return articles
        seen = set()
        cards = soup.find_all('div', class_=re.compile(r'p-articleCard'))
        for card in cards:
            title_tag = card.find('p', class_='p-articleCard__title')
            if not title_tag or not title_tag.find('a'): continue
            a_tag = title_tag.find('a')
            title = a_tag.get_text(strip=True)
            href = a_tag['href']
            full_url = urllib.parse.urljoin("https://www.cinra.net/", href)
            if 'job.cinra.net' in full_url or full_url in seen: continue
            seen.add(full_url)
            lead_tag = card.find('p', class_='p-articleCard__lead')
            summary = lead_tag.get_text(strip=True) if lead_tag else "（請點擊標題閱讀原文）"
            author_tag = card.find('span', class_='c-author__name')
            author = author_tag.get_text(strip=True).replace('by ', '').strip() if author_tag else ""
            date_tag = card.find('p', class_='p-articleCard__date')
            published = date_tag.get_text(strip=True).replace('.', '-') if date_tag else "最新"
            img_tag = card.find('img')
            img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
            articles.append({"Source": "CINRA", "Title": title, "Link": full_url, "Published": published, "Summary": format_summary(summary, author), "Image": img_url})
            if len(articles) >= 15: break
    except Exception as e: print(f"CINRA 錯誤: {e}")
    return articles

def fetch_sabukaru():
    articles = []
    try:
        soup = get_soup("https://sabukaru.online/articles")
        if not soup: return articles
        seen = set()
        items = soup.find_all('article', class_=re.compile(r'BlogList-item'))
        valid_links = []
        for item in items:
            a_tag = item.find('a', class_='Blog-header-content-link')
            title_tag = item.find('h2', class_='Blog-title')
            if not a_tag or not title_tag: continue
            href = a_tag['href']
            full_url = urllib.parse.urljoin("https://sabukaru.online", href)
            title = title_tag.get_text(strip=True)
            if full_url in seen: continue
            seen.add(full_url)
            author_tag = item.find('a', class_='Blog-meta-item--author')
            author = author_tag.get_text(strip=True) if author_tag else ""
            time_tag = item.find('time', class_='Blog-meta-item--date')
            published = time_tag['datetime'] if time_tag and time_tag.has_attr('datetime') else "最新"
            img_tag = item.find('img')
            img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
            valid_links.append({"title": title, "url": full_url, "author": author, "published": published, "img_url": img_url})
            if len(valid_links) >= 15: break
        def process_link(data):
            art_soup = get_soup(data["url"])
            summary = ""
            if art_soup:
                og_desc = art_soup.find('meta', property='og:description')
                summary = og_desc['content'] if og_desc and og_desc.get('content') else ""
                if not summary or len(summary) < 20:
                    paragraphs = [p.get_text(strip=True) for p in art_soup.find_all('p') if len(p.get_text(strip=True)) > 40]
                    summary = " ".join(paragraphs[:3]) if paragraphs else "（請點擊標題閱讀原文）"
            return {"Source": "Sabukaru", "Title": data["title"], "Link": data["url"], "Published": data["published"], "Summary": format_summary(summary, data["author"]), "Image": data["img_url"]}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            articles = [res for res in ex.map(process_link, valid_links) if res]
    except Exception as e: print(f"Sabukaru 錯誤: {e}")
    return articles

def fetch_biede():
    articles = []
    try:
        soup = get_soup("https://www.biede.com/")
        if not soup: return articles
        seen = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            full_url = urllib.parse.urljoin("https://www.biede.com/", href)
            if ('/article/' in href or '/post/' in href) and full_url not in seen:
                seen.add(full_url)
                title = a.get_text(strip=True)
                if len(title) < 5:
                    h_tag = a.find(['h2', 'h3', 'h4', 'p'])
                    title = h_tag.get_text(strip=True) if h_tag else title
                if len(title) < 5: continue
                art_soup = get_soup(full_url)
                author = ""
                text = "（請點擊標題閱讀原文紀實）"
                img_url = None
                if art_soup:
                    og_img = art_soup.find('meta', property='og:image')
                    img_url = og_img['content'] if og_img else None
                    author_meta = art_soup.find('meta', attrs={'name': 'author'}) or art_soup.find('div', class_=re.compile(r'author'))
                    author = author_meta.get_text(strip=True) if author_meta and not author_meta.get('content') else (author_meta['content'] if author_meta else "")
                    paragraphs = [p.get_text(strip=True) for p in art_soup.find_all('p') if len(p.get_text(strip=True)) > 40]
                    if paragraphs: text = " ".join(paragraphs[:3])
                articles.append({"Source": "BIE別的", "Title": title, "Link": full_url, "Published": "最新", "Summary": format_summary(text, author), "Image": img_url})
                if len(articles) >= 10: break
    except Exception as e: print(f"BIE別的 錯誤: {e}")
    return articles

def fetch_tripleampersand():
    articles = []
    try:
        soup = get_soup("https://tripleampersand.org/")
        if not soup: return articles
        seen = set()
        posts = soup.find_all('div', class_='index-post')
        for post in posts[:15]:
            title_tag = post.find('h2').find('a') if post.find('h2') else None
            if not title_tag: continue
            title = title_tag.get_text(strip=True)
            link = title_tag['href']
            if link in seen: continue
            seen.add(link)
            author_tag = post.select_one('.authors li a')
            author = author_tag.get_text(strip=True) if author_tag else ""
            img_tag = post.select_one('.post-img img')
            img_url = img_tag['src'] if img_tag else None
            text_div = post.find('div', class_='text')
            summary = text_div.get_text(" ", strip=True) if text_div else ""
            summary = summary.replace("Read More »", "").strip()
            articles.append({"Source": "TripleAmpersand", "Title": title, "Link": link, "Published": "最新", "Summary": format_summary(summary, author), "Image": img_url})
    except Exception as e: print(f"TripleAmpersand 錯誤: {e}")
    return articles

# 🌟 新增：觸樂夜話專屬爬蟲
def fetch_chuapp():
    articles = []
    try:
        # 直接進入「觸樂怪話 / 夜話」的分類頁面
        soup = get_soup("http://www.chuapp.com/tag/index/id/20369.html")
        if not soup: return articles
        
        container = soup.find('div', class_='category-list')
        if not container: return articles
        
        seen = set()
        # 夜話列表結構為 a.fn-clear
        for a in container.find_all('a', class_='fn-clear', recursive=False):
            href = a.get('href')
            if not href or not href.startswith('/article/'): continue
            
            full_url = urllib.parse.urljoin("http://www.chuapp.com", href)
            if full_url in seen: continue
            seen.add(full_url)
            
            title = a.get('title', '')
            if not title:
                dt = a.find('dt')
                title = dt.get_text(strip=True) if dt else "未知標題"
            
            img = a.find('img')
            img_url = img.get('src') if img else None
            
            dl = a.find('dl')
            author, published, summary = "", "最新", "（請點擊標題閱讀原文）"
            
            if dl:
                em = dl.find('em')
                author = em.get_text(strip=True) if em else ""
                
                span = dl.find('span', class_='fn-left')
                if span:
                    # 濾除作者名稱，保留時間字串，例如「05月15日」
                    published = span.get_text(strip=True).replace(author, '').strip()
                    
                dds = dl.find_all('dd')
                if len(dds) > 1:
                    summary = dds[1].get_text(strip=True)
            
            articles.append({
                "Source": "触乐",
                "Title": title,
                "Link": full_url,
                "Published": published,
                "Summary": format_summary(summary, author),
                "Image": img_url
            })
            
            if len(articles) >= 15: break
            
    except Exception as e: 
        print(f"触乐 錯誤: {e}")
        
    return articles

# ==========================================
# 主程式排程
# ==========================================
def main():
    print("🚀 開始執行資料抓取與同步...")
    all_articles = []
    
    # 🌟 新增：FNMNL (快訊) 與 The Comics Journal (評論)
    rss_sources = [
        ("https://aeon.co/feed.rss", "Aeon 思想誌", 15, True),
        ("https://www.newyorker.com/feed/culture/rss", "New Yorker, Books and Culture", 15, True),
        ("https://www.421.news/en/rss/", "421 News (EN)", 15, False),
        ("https://www.421.news/zh/rss/", "421 News (ZH)", 15, False),
        ("https://www.linking.vision/feed/", "聯經思想空間", 15, False),
        ("https://feedx.net/rss/shanghaishuping.xml", "上海書評", 15, False),
        ("https://www.leapleapleap.com/feed/", "藝術界", 15, False),
        ("https://www.versobooks.com/blogs/news.atom", "Verso Blog", 15, False),
        ("https://wired.jp/feed/rss", "WIRED.jp", 15, True),
        ("https://radii.co/feed", "Radii", 15, True),
        ("https://www.tcj.com/feed/", "The Comics Journal", 15, True), # 深度評論解析
        ("https://fnmnl.tv/feed/", "FNMNL", 15, False),               # 音樂/街頭快訊
        ("https://dukeupress.wordpress.com/feed/", "Duke Press", 15, False),
        ("https://asianreviewofbooks.com/feed/", "Asian Review of Books", 15, False),
        ("https://u.osu.edu/mclc/feed/", "MCLC Resource Center", 15, False),
        ("https://tyingknots.net/feed/", "结绳志", 15, False)
        
    ]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_rss, url, name, limit, deep) for url, name, limit, deep in rss_sources]
        
        # 🌟 新增：fetch_chuapp 至客製化爬蟲陣列
        custom_scrapers = [
            fetch_webgenron, fetch_eflux, fetch_funambulist, 
            fetch_mit_reader, fetch_eurozine, fetch_bijutsutecho, 
            fetch_thepaper, fetch_thepoint, fetch_verse, fetch_cinra, 
            fetch_jiemian, fetch_sabukaru, fetch_biede,
            fetch_tripleampersand, fetch_chuapp
        ]
        futures.extend([executor.submit(func) for func in custom_scrapers])
        
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res: all_articles.extend(res)

    if all_articles:
        db = get_db_client()
        if not db:
            print("❌ 找不到 Turso 環境變數，跳過同步。")
            return

        try:
            links_to_check = [a['Link'] for a in all_articles]
            existing_dates = {}
            try:
                chunk_size = 50
                for i in range(0, len(links_to_check), chunk_size):
                    chunk = links_to_check[i:i + chunk_size]
                    placeholders = ','.join(['?'] * len(chunk))
                    res = db.execute(f"SELECT Link, SortDate FROM articles WHERE Link IN ({placeholders})", chunk)
                    for row in res.rows:
                        existing_dates[row[0]] = row[1]
            except Exception as e:
                print(f"⚠️ 獲取歷史時間失敗 (不影響寫入): {e}")

            cleaned_articles = []
            for a in all_articles:
                article_data = a.copy()
                has_valid_date = False
                
                if article_data.get('Published') and not any(k in str(article_data['Published']) for k in ["最新", "Issue", "刊", "歷史歸檔"]):
                    try:
                        # 觸樂抓下來的「05月15日」等無年份時間字串，如果失敗會自動被指派 utcnow()
                        dt = pd.to_datetime(article_data['Published'], errors='coerce', utc=True)
                        if not pd.isna(dt):
                            article_data['Published'] = dt.strftime('%Y-%m-%d')
                            article_data['SortDate'] = dt.isoformat()
                            has_valid_date = True
                    except: pass
                
                if not has_valid_date:
                    if article_data['Link'] in existing_dates:
                        article_data['SortDate'] = existing_dates[article_data['Link']]
                    else:
                        article_data['SortDate'] = datetime.utcnow().isoformat()
                        
                cleaned_articles.append(article_data)

            sql = """
            INSERT INTO articles (Source, Title, Link, Published, Summary, Image, SortDate, is_bookmarked)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(Link) DO UPDATE SET 
                Title=excluded.Title,
                Published=excluded.Published,
                Summary=excluded.Summary,
                Image=excluded.Image;
            """
            
            success_count = 0
            error_count = 0
            
            for art in cleaned_articles:
                args = [
                    art['Source'], art['Title'], art['Link'], 
                    art['Published'], art['Summary'], art['Image'], art['SortDate']
                ]
                
                try:
                    db.execute(sql, args)
                    success_count += 1
                except Exception as inner_e:
                    print(f"⚠️ 單筆寫入失敗 ({art['Title'][:10]}...): {inner_e}")
                    error_count += 1
                    
            print(f"✅ 成功同步 {success_count} 篇文章至 Turso 資料庫！(失敗: {error_count} 筆)")
            
        except Exception as e:
            print(f"❌ 同步過程發生嚴重錯誤: {e}")
            
        finally:
            if db:
                db.close()
                print("🔌 資料庫連線已安全關閉。")

    else:
        print("❌ 未抓取到任何資料。")

if __name__ == "__main__":
    main()
