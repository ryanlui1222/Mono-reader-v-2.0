import os
import re
import requests
import cloudscraper
import base64
import libsql_client
import urllib.parse
from bs4 import BeautifulSoup

# ==========================================
# 1. 取得環境變數
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# ==========================================
# 🛡️ 安全圖片下載器 (支援 Base64 轉換)
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
            encoded_str = base64.b64encode(res.content).decode('utf-8')
            content_type = res.headers.get('Content-Type', 'image/jpeg')
            return f"data:{content_type};base64,{encoded_str}"
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

    # --- 4. Google Books (精準搜尋與降噪盲搜) ---
    if clean_isbn:
        try:
            res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q={clean_isbn}", timeout=5).json()
            if "items" in res:
                img = res["items"][0].get("volumeInfo", {}).get("imageLinks", {}).get("thumbnail")
                if img: return get_secure_image_base64(img.replace("http://", "https://"), "google")
        except: pass

    try:
        short_title = re.sub(r'[^a-zA-Z0-9\s]', '', title.split(':')[0].strip())
        query = urllib.parse.quote(f"{short_title} {author.split(',')[0]}")
        res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q={query}", timeout=5).json()
        if "items" in res:
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
                "publisher_journal": "青土社", "issue_volume": "", "identifier": identifier, "publish_date": "2026-05", 
                "abstract": "（青土社新刊）", "link": link, "image": image_url
            })
        return records
    except: return []

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
