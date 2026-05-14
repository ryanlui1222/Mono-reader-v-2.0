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
from supabase import create_client, Client

# ==========================================
# 全局網路引擎 & 基礎設定
# ==========================================
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
TIMEOUT = 15

# ==========================================
# 🛠️ 輔助函數 (Helpers) - 大幅減少重複程式碼
# ==========================================
def get_soup(url, custom_headers=HEADERS):
    """通用的 HTML 獲取與解析器"""
    try:
        res = scraper.get(url, headers=custom_headers, timeout=TIMEOUT)
        return BeautifulSoup(res.text, 'html.parser') if res.status_code == 200 else None
    except:
        return None

def format_summary(text, author="", max_len=None):
    """通用的摘要清洗、字數計算與作者排版器"""
    if not text: return "（無提供文字摘要）"
    text = " ".join(text.split()) # 清除多餘空白與換行
    
    # 計算英文比例決定截斷長度 (若無強制指定 max_len)
    if not max_len:
        eng_count = sum(1 for c in text[:50] if c.isalpha() and c.isascii())
        max_len = 600 if eng_count > 25 else 200 
        
    summary = text[:max_len] + '...' if len(text) > max_len else text
    return f"**👤 著者：** {author}\n\n{summary}" if author else summary

# ==========================================
# ☁️ Supabase 雲端資料庫同步模組
# ==========================================
def sync_to_supabase(articles):
    """將抓取到的文章列表同步至 Supabase"""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        print("❌ 找不到 Supabase 環境變數，跳過同步。請確認 GitHub Actions 的 Secrets 已正確設定。")
        return
    
    supabase: Client = create_client(url, key)
    
    if articles:
        try:
            # 核心邏輯：Upsert (以 Link 為唯一值進行衝突檢查)
            # on_conflict='Link' 確保文章不重複且永久保留。
            # 由於我們沒有傳入 is_bookmarked 欄位，資料庫會保留已存在的書籤狀態！
            supabase.table('articles').upsert(articles, on_conflict='Link').execute()
            print(f"✅ 成功同步 {len(articles)} 篇文章至雲端資料庫！")
        except Exception as e:
            print(f"❌ 同步失敗: {e}")

# ==========================================
# 🕷️ 各平台專屬爬蟲模組
# ==========================================
def fetch_rss(feed_url, source_name, limit=20, deep_fetch=False):
    articles = []
    try:
        parsed = feedparser.parse(scraper.get(feed_url, timeout=TIMEOUT).content)
        
        def process_entry(entry):
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
                    
                    paragraphs = [p.get_text(strip=True) for p in art_soup.find_all('p') if len(p.get_text(strip=True)) > 60]
                    clean_p = [p for p in paragraphs if not any(bad in p.lower() for bad in ["subscribe", "newsletter", "sign up"])]
                    if clean_p: text = " ".join(clean_p[:3])
            
            return {
                "Source": source_name, "Title": entry.title, "Link": entry.link,
                "Published": entry.get('published', '最新'),
                "Summary": format_summary(text), "Image": img_url
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
        
        # 精準鎖定「最新一期」的專屬區塊
        latest_section = soup.find('div', class_='section-top')
        if not latest_section: return articles
        
        issue_tag = latest_section.find('h1')
        issue_num = issue_tag.get_text(strip=True) if issue_tag else "最新刊"
        source_name = f"The Point ({issue_num})"
        
        pattern = re.compile(r'https://thepointmag\.com/(examined-life|politics|criticism|dialogue|letter|correspondence)/([^/]+)/?$')
        
        links = []
        for a in latest_section.find_all('a', href=True):
            href = a['href']
            if pattern.match(href) and href not in links:
                links.append(href)
        
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
            
    except Exception as e: 
        print(f"The Point 錯誤: {e}")
