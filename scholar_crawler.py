import os
import re
import requests
import cloudscraper
import libsql_client
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime
import urllib.parse

# ==========================================
# 1. 取得環境變數
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# ==========================================
# 🌟 智慧封面搜尋引擎 (支援無 ISBN 書名盲搜)
# ==========================================
def get_best_cover(isbn, title, author, publisher):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # 1. MIT Press 專屬 CDN
    if publisher == "MIT Press" and isbn:
        img_url = f"https://mit-press-new-us.imgix.net/covers/{isbn}.jpg"
        try:
            if requests.head(img_url, headers=headers, timeout=5).status_code == 200:
                return img_url
        except: pass

    # 2. Google Books (精準 ISBN 搜尋)
    if isbn:
        try:
            res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}", timeout=5)
            data = res.json()
            if "items" in data:
                img_links = data["items"][0].get("volumeInfo", {}).get("imageLinks", {})
                best = img_links.get("thumbnail") or img_links.get("smallThumbnail")
                if best: return best.replace("http://", "https://")
        except: pass

    # 3. Google Books (無 ISBN 救援：利用書名 + 作者盲搜)
    try:
        # 去除副標題，提高搜尋命中率
        clean_title = urllib.parse.quote(title.split(':')[0])
        res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=intitle:{clean_title}", timeout=5)
        data = res.json()
        if "items" in data:
            for item in data["items"]:
                vol_info = item.get("volumeInfo", {})
                api_authors = " ".join(vol_info.get("authors", [])).lower()
                # 簡單驗證作者姓氏是否吻合
                author_last_name = author.split(' ')[-1].lower() if author else ""
                if author_last_name in api_authors or not author_last_name:
                    img_links = vol_info.get("imageLinks", {})
                    best = img_links.get("thumbnail") or img_links.get("smallThumbnail")
                    if best: return best.replace("http://", "https://")
    except: pass

    # 4. Open Library (嚴格確認有圖才回傳，避免前端塞入 1x1 空白像素)
    if isbn:
        try:
            ol_url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json"
            if requests.get(ol_url, timeout=5).json():
                return f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
        except: pass

    return ""

# ==========================================
# 2. 爬蟲模組 A：Crossref API
# ==========================================
def fetch_from_crossref(member_id, publisher_name):
    print(f"🔍 [Crossref] 準備擷取 {publisher_name} 新書...")
    
    types_to_fetch = ["book", "monograph"]
    headers = {"User-Agent": "BiblioappCloud/1.0"}
    all_items = []
    
    for t in types_to_fetch:
        url = f"https://api.crossref.org/members/{member_id}/works"
        params = {"filter": f"type:{t}", "sort": "published", "order": "desc", "rows": 15}
        try:
            res = requests.get(url, params=params, headers=headers, timeout=15)
            if res.status_code == 200:
                all_items.extend(res.json().get("message", {}).get("items", []))
        except Exception as e:
            print(f"⚠️ 取得 {t} 失敗: {e}")
            
    def get_sort_date(item):
        date_obj = item.get("issued") or item.get("published-print") or item.get("published-online") or {}
        parts = date_obj.get("date-parts", [[0]])[0]
        year = parts[0] if len(parts) > 0 and parts[0] else 0
        month = parts[1] if len(parts) > 1 and parts[1] else 1
        return (year, month)

    all_items.sort(key=get_sort_date, reverse=True)
    top_items = all_items[:20]
    
    records = []
    for item in top_items:
        try:
            title = item.get("title", ["未命名書籍"])[0]
            authors_list = item.get("author", [])
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list]) or publisher_name
            
            date_obj = item.get("issued") or item.get("published-print") or item.get("published-online") or {}
            date_parts = date_obj.get("date-parts", [[]])[0]
            pub_date = f"{date_parts[0]}-{date_parts[1]:02d}" if len(date_parts) >= 2 else str(date_parts[0]) if date_parts else "未知日期"
            
            doi = item.get("DOI", "")
            isbn_list = item.get("ISBN", [])
            isbn_clean = re.sub(r'[^0-9X]', '', str(isbn_list[0])) if isbn_list else ""
            identifier = isbn_clean if isbn_clean else doi
            link = item.get("URL", f"https://doi.org/{doi}")
            raw_abstract = item.get("abstract", "")
            abstract = re.sub(r'<[^>]+>', '', raw_abstract) if raw_abstract else "（官方暫無提供數位摘要）"
            
            # 🌟 傳入書名與作者，啟動雙重驗證盲搜
            image_url = get_best_cover(isbn_clean, title, author, publisher_name)

            records.append({
                "type": "Book", "title": title, "author": author,
                "publisher_journal": publisher_name, "issue_volume": "",
                "identifier": identifier, "publish_date": pub_date,
                "abstract": abstract[:600] + "..." if len(abstract) > 600 else abstract,
                "link": link, "image": image_url
            })
        except Exception as e:
            pass
            
    return records
# ==========================================
# 2. 爬蟲模組 A：Crossref API (適用 MIT & Duke)
# ==========================================
def fetch_from_crossref(member_id, publisher_name):
    print(f"🔍 [Crossref] 準備擷取 {publisher_name} 新書...")
    
    # 同時抓取 book 與 monograph，避免漏掉學術專書
    types_to_fetch = ["book", "monograph"]
    headers = {"User-Agent": "BiblioappCloud/1.0 (mailto:admin@monoreader.cloud)"}
    all_items = []
    
    for t in types_to_fetch:
        url = f"https://api.crossref.org/members/{member_id}/works"
        params = {"filter": f"type:{t}", "sort": "published", "order": "desc", "rows": 15}
        try:
            res = requests.get(url, params=params, headers=headers, timeout=15)
            if res.status_code == 200:
                all_items.extend(res.json().get("message", {}).get("items", []))
        except Exception as e:
            print(f"⚠️ 取得 {t} 失敗: {e}")
            
    # 依照精準日期排序
    def get_sort_date(item):
        date_obj = item.get("issued") or item.get("published-print") or item.get("published-online") or {}
        parts = date_obj.get("date-parts", [[0]])[0]
        year = parts[0] if len(parts) > 0 and parts[0] else 0
        month = parts[1] if len(parts) > 1 and parts[1] else 1
        return (year, month)

    all_items.sort(key=get_sort_date, reverse=True)
    top_items = all_items[:20] # 取最新的 20 筆
    
    records = []
    for item in top_items:
        try:
            title = item.get("title", ["未命名書籍"])[0]
            authors_list = item.get("author", [])
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list]) or publisher_name
            
            date_obj = item.get("issued") or item.get("published-print") or item.get("published-online") or {}
            date_parts = date_obj.get("date-parts", [[]])[0]
            
            if len(date_parts) >= 2:
                pub_date = f"{date_parts[0]}-{date_parts[1]:02d}"
            elif len(date_parts) == 1 and date_parts[0]:
                pub_date = str(date_parts[0])
            else:
                pub_date = "未知日期"
            
            doi = item.get("DOI", "")
            isbn_list = item.get("ISBN", [])
            isbn_clean = re.sub(r'[^0-9X]', '', str(isbn_list[0])) if isbn_list else ""
            identifier = isbn_clean if isbn_clean else doi
            
            link = item.get("URL", f"https://doi.org/{doi}")
            raw_abstract = item.get("abstract", "")
            abstract = re.sub(r'<[^>]+>', '', raw_abstract) if raw_abstract else "（官方暫無提供數位摘要）"
            
            # 呼叫升級版的找圖引擎
            image_url = get_best_cover(isbn_clean, publisher_name, link)

            records.append({
                "type": "Book", "title": title, "author": author,
                "publisher_journal": publisher_name, "issue_volume": "",
                "identifier": identifier, "publish_date": pub_date,
                "abstract": abstract[:600] + "..." if len(abstract) > 600 else abstract,
                "link": link, "image": image_url
            })
        except Exception as e:
            print(f"⚠️ 解析單本書籍時發生錯誤: {e}")
            
    return records

# ==========================================
# 3. 爬蟲模組 B：青土社 (網頁 HTML 解析)
# ==========================================
def crawl_seidosha():
    print("🔍 [青土社] 準備擷取 新刊/雜誌...")
    url = "https://www.seidosha.co.jp/"
    records = []
    
    try:
        res = requests.get(url, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, "html.parser")
        
        new_mag_section = soup.find("div", id="new_mag")
        if not new_mag_section: return records
            
        items = new_mag_section.find_all("div", class_="col-link-items")
        for item in items:
            a_tag = item.find("a")
            if not a_tag: continue
            
            raw_link = a_tag.get("href", "")
            link = f"https://www.seidosha.co.jp{raw_link.lstrip('.')}"
            
            img_tag = item.find("img")
            raw_img = img_tag.get("src", "") if img_tag else ""
            image_url = f"https://www.seidosha.co.jp{raw_img}" if raw_img else ""
            
            identifier = link
            isbn_match = re.search(r'(\d{13})\.jpg', raw_img)
            if isbn_match:
                identifier = isbn_match.group(1)
                
            title_tag = item.find("h3", class_="h5")
            title = title_tag.get_text(strip=True) if title_tag else "未命名書籍"
            
            author_tag = item.find("p", class_="author")
            author = author_tag.get_text(strip=True) if author_tag else "青土社"
            
            date_tag = item.find("p", class_="date")
            pub_date = date_tag.get_text(strip=True) if date_tag else ""
            pub_date = pub_date.replace("年", "-").replace("月", "-").replace("日", "")
            
            pub_type = "Journal" if "ユリイカ" in title or "現代思想" in title else "Book"
            
            records.append({
                "type": pub_type, "title": title, "author": author,
                "publisher_journal": "青土社", "issue_volume": "",
                "identifier": identifier, "publish_date": pub_date,
                "abstract": "（此為青土社新刊目錄擷取，無詳細摘要）",
                "link": link, "image": image_url
            })
    except Exception as e:
        print(f"❌ [青土社] 擷取發生錯誤: {e}")
    return records

# ==========================================
# 4. 寫入 Turso 資料庫
# ==========================================
def save_to_db(items):
    if not items: return
    if not TURSO_DATABASE_URL or not TURSO_TOKEN:
        print("❌ 錯誤：找不到 TURSO_DATABASE_URL 或 Token。")
        return
        
    client = libsql_client.create_client_sync(url=TURSO_DATABASE_URL, auth_token=TURSO_TOKEN)
    success_count = 0
    try:
        for item in items:
            sql = """
            INSERT INTO academic_pubs 
            (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(identifier) DO UPDATE SET 
                title=excluded.title, author=excluded.author, 
                publish_date=excluded.publish_date, image=excluded.image;
            """
            client.execute(sql, [
                item["type"], item["title"], item["author"], item["publisher_journal"], 
                item["issue_volume"], item["identifier"], item["publish_date"], 
                item["abstract"], item["link"], item["image"]
            ])
            success_count += 1
        print(f"✅ 成功寫入/更新 {success_count} 筆文獻！")
    except Exception as e:
        print(f"❌ 寫入資料庫時發生錯誤: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    all_records = []
    
    # 執行所有爬蟲模組
    all_records.extend(fetch_from_crossref("281", "MIT Press"))            
    all_records.extend(fetch_from_crossref("73", "Duke University Press")) 
    all_records.extend(crawl_seidosha())                                   
    
    print(f"📥 總計取得 {len(all_records)} 筆資料，準備寫入資料庫...")
    save_to_db(all_records)
