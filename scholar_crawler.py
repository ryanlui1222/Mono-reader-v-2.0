import os
import re
import requests
import libsql_client
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================================
# 1. 取得環境變數
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# ==========================================
# 2. 智慧封面搜尋引擎
# ==========================================
def get_best_cover(isbn, title, author, publisher):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # --- A. MIT Press 專屬 CDN (精準匹配) ---
    if publisher == "MIT Press" and isbn:
        img_url = f"https://mit-press-new-us.imgix.net/covers/{isbn}.jpg"
        if requests.head(img_url, headers=headers, timeout=5).status_code == 200:
            return img_url

    # --- B. Google Books API (ISBN 搜尋) ---
    if isbn:
        try:
            # 移除 isbn: 前綴，改為直接搜尋，增加命中率
            res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q={isbn}", timeout=5)
            data = res.json()
            if "items" in data:
                img_links = data["items"][0].get("volumeInfo", {}).get("imageLinks", {})
                best = img_links.get("thumbnail") or img_links.get("smallThumbnail")
                if best: return best.replace("http://", "https://")
        except: pass

    # --- C. Google Books (書名+作者盲搜) ---
    try:
        query = urllib.parse.quote(f"{title} {author.split(',')[0]}")
        res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q={query}", timeout=5)
        data = res.json()
        if "items" in data:
            img_links = data["items"][0].get("volumeInfo", {}).get("imageLinks", {})
            best = img_links.get("thumbnail") or img_links.get("smallThumbnail")
            if best: return best.replace("http://", "https://")
    except: pass

    return ""

# ==========================================
# 3. 爬蟲核心 (整合版)
# ==========================================
def fetch_from_crossref(member_id, publisher_name):
    print(f"🔍 [Crossref] 正在擷取 {publisher_name}...")
    url = f"https://api.crossref.org/members/{member_id}/works"
    # 擴大搜尋範圍：抓更多筆資料
    params = {"filter": "type:book,type:monograph", "sort": "published", "order": "desc", "rows": 30}
    headers = {"User-Agent": "BiblioappCloud/1.0"}
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)
        items = res.json().get("message", {}).get("items", [])
        print(f"   -> 找到 {len(items)} 筆出版紀錄")
        
        records = []
        for item in items:
            title = item.get("title", ["未命名書籍"])[0]
            authors_list = item.get("author", [])
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list]) or publisher_name
            
            date_obj = item.get("issued") or item.get("published-print") or {}
            date_parts = date_obj.get("date-parts", [[]])[0]
            pub_date = f"{date_parts[0]}-{date_parts[1]:02d}" if len(date_parts) >= 2 else str(date_parts[0]) if date_parts else "未知日期"
            
            isbn_list = item.get("ISBN", [])
            isbn_clean = re.sub(r'[^0-9X]', '', str(isbn_list[0])) if isbn_list else ""
            link = item.get("URL", f"https://doi.org/{item.get('DOI', '')}")
            
            # 🌟 執行找圖引擎
            image_url = get_best_cover(isbn_clean, title, author, publisher_name)
            
            records.append({
                "type": "Book", "title": title, "author": author,
                "publisher_journal": publisher_name, "issue_volume": "",
                "identifier": isbn_clean or link, "publish_date": pub_date,
                "abstract": "（API 擷取資訊）", "link": link, "image": image_url
            })
        return records
    except Exception as e:
        print(f"❌ [{publisher_name}] 擷取失敗: {e}")
        return []

def crawl_seidosha():
    print("🔍 [青土社] 準備擷取...")
    try:
        res = requests.get("https://www.seidosha.co.jp/", timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.find("div", id="new_mag").find_all("div", class_="col-link-items")
        records = []
        for item in items:
            a_tag = item.find("a")
            link = f"https://www.seidosha.co.jp{a_tag.get('href', '').lstrip('.')}"
            title = item.find("h3", class_="h5").get_text(strip=True)
            img_src = item.find("img").get("src", "")
            image_url = f"https://www.seidosha.co.jp{img_src}"
            records.append({
                "type": "Journal" if "ユリイカ" in title or "現代思想" in title else "Book",
                "title": title, "author": item.find("p", class_="author").get_text(strip=True) or "青土社",
                "publisher_journal": "青土社", "issue_volume": "",
                "identifier": link, "publish_date": "2026-05", 
                "abstract": "（青土社新刊）", "link": link, "image": image_url
            })
        return records
    except: return []

# ==========================================
# 4. 寫入資料庫
# ==========================================
def save_to_db(items):
    client = libsql_client.create_client_sync(url=TURSO_DATABASE_URL, auth_token=TURSO_TOKEN)
    for item in items:
        sql = """INSERT INTO academic_pubs (type, title, author, publisher_journal, identifier, publish_date, abstract, link, image)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                 ON CONFLICT(identifier) DO UPDATE SET image=excluded.image;"""
        client.execute(sql, [item["type"], item["title"], item["author"], item["publisher_journal"], 
                             item["identifier"], item["publish_date"], item["abstract"], item["link"], item["image"]])
    client.close()
    print("✅ 資料庫更新完成。")

if __name__ == "__main__":
    all_books = []
    all_books.extend(fetch_from_crossref("281", "MIT Press"))
    all_books.extend(fetch_from_crossref("73", "Duke University Press"))
    all_books.extend(crawl_seidosha())
    save_to_db(all_books)
