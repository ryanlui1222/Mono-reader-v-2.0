import os
import re
import requests
import cloudscraper
import libsql_client
import urllib.parse
from bs4 import BeautifulSoup

# ==========================================
# 1. 取得環境變數與金鑰
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# 👇 請在這裡填入您的 LibraryThing Developer Key
LIBRARYTHING_DEV_KEY = "請貼上您的Key"

# ==========================================
# 🌟 智慧封面搜尋引擎 (五重降落傘)
# ==========================================
def get_best_cover(isbn, title, author, publisher):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # --- 1. MIT Press 專屬 CDN ---
    if publisher == "MIT Press" and isbn:
        img_url = f"https://mit-press-new-us.imgix.net/covers/{isbn}.jpg"
        try:
            if requests.head(img_url, headers=headers, timeout=5).status_code == 200:
                return img_url
        except: pass

    # --- 2. LibraryThing API (官方封面介面) ---
    if LIBRARYTHING_DEV_KEY and LIBRARYTHING_DEV_KEY != "請貼上您的Key" and isbn:
        lt_url = f"http://covers.librarything.com/devkey/{LIBRARYTHING_DEV_KEY}/large/isbn/{isbn}"
        try:
            res = requests.get(lt_url, timeout=5)
            # 排除 1x1 像素的假圖片 (小於 100 bytes)
            if res.status_code == 200 and len(res.content) > 100:
                return lt_url
        except: pass

    # --- 3. Google Books API (ISBN 搜尋) ---
    if isbn:
        try:
            res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q={isbn}", timeout=5)
            data = res.json()
            if "items" in data:
                img_links = data["items"][0].get("volumeInfo", {}).get("imageLinks", {})
                best = img_links.get("thumbnail") or img_links.get("smallThumbnail")
                if best: return best.replace("http://", "https://")
        except: pass

    # --- 4. Google Books API (極端暴力盲搜：僅用書名前半段) ---
    try:
        # 去掉副標題，去掉特殊符號，只留下最核心的英文字
        short_title = re.sub(r'[^a-zA-Z0-9\s]', '', title.split(':')[0].strip())
        query = urllib.parse.quote(short_title)
        res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q={query}", timeout=5)
        data = res.json()
        if "items" in data:
            img_links = data["items"][0].get("volumeInfo", {}).get("imageLinks", {})
            best = img_links.get("thumbnail") or img_links.get("smallThumbnail")
            if best: return best.replace("http://", "https://")
    except: pass

    # --- 5. Open Library (最終備用) ---
    if isbn:
        try:
            ol_url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json"
            if requests.get(ol_url, timeout=5).json():
                return f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
        except: pass

    return ""

# ==========================================
# 3. 爬蟲核心
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
            
            # 傳入強化的封面搜尋引擎
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
            raw_link = a_tag.get("href", "")
            link = f"https://www.seidosha.co.jp{raw_link.lstrip('.')}"
            
            identifier = link
            id_match = re.search(r'id=(\d+)', link)
            if id_match: identifier = f"seidosha_{id_match.group(1)}"
                
            title = item.find("h3", class_="h5").get_text(strip=True)
            img_src = item.find("img").get("src", "")
            image_url = f"https://www.seidosha.co.jp{img_src}"
            records.append({
                "type": "Journal" if "ユリイカ" in title or "現代思想" in title else "Book",
                "title": title, "author": item.find("p", class_="author").get_text(strip=True) or "青土社",
                "publisher_journal": "青土社", "issue_volume": "",
                "identifier": identifier, "publish_date": "2026-05", 
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
                 ON CONFLICT(identifier) DO UPDATE SET image=excluded.image, title=excluded.title;"""
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
