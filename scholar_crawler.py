import os
import re
import requests
import libsql_client
from datetime import datetime

# ==========================================
# 1. 取得環境變數
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# ==========================================
# 2. 共用的 API 爬蟲邏輯 (避免重複程式碼)
# ==========================================
def fetch_from_crossref(member_id, publisher_name):
    print(f"🔍 準備透過 Crossref API 擷取 {publisher_name}...")
    url = f"https://api.crossref.org/members/{member_id}/works"
    params = {"filter": "type:book", "sort": "published", "order": "desc", "rows": 15}
    headers = {"User-Agent": "BiblioappCloud/1.0 (mailto:admin@monoreader.cloud)"}
    
    records = []
    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)
        res.raise_for_status()
        items = res.json().get("message", {}).get("items", [])
        
        for item in items:
            title = item.get("title", ["未命名書籍"])[0]
            authors_list = item.get("author", [])
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list]) or publisher_name
            
            date_parts = item.get("published", {}).get("date-parts", [[]])[0]
            pub_date = f"{date_parts[0]}-{date_parts[1]:02d}" if len(date_parts) >= 2 else str(date_parts[0]) if date_parts else "未知日期"
            
            doi = item.get("DOI", "")
            isbn_list = item.get("ISBN", [])
            isbn_clean = re.sub(r'[^0-9X]', '', str(isbn_list[0])) if isbn_list else ""
            identifier = isbn_clean if isbn_clean else doi
            
            link = item.get("URL", f"https://doi.org/{doi}")
            raw_abstract = item.get("abstract", "")
            abstract = re.sub(r'<[^>]+>', '', raw_abstract) if raw_abstract else "（官方暫無提供數位摘要）"
            
            # 使用 Open Library 自動補齊書封
            image_url = f"https://covers.openlibrary.org/b/isbn/{isbn_clean}-L.jpg" if isbn_clean else ""

            records.append({
                "type": "Book", "title": title, "author": author,
                "publisher_journal": publisher_name, "issue_volume": "",
                "identifier": identifier, "publish_date": pub_date,
                "abstract": abstract[:600] + "..." if len(abstract) > 600 else abstract,
                "link": link, "image": image_url
            })
    except Exception as e:
        print(f"❌ [{publisher_name}] 擷取失敗: {e}")
    return records

# ==========================================
# 3. 寫入 Turso 資料庫
# ==========================================
def save_to_db(items):
    if not TURSO_DATABASE_URL or not TURSO_TOKEN: return
    client = libsql_client.create_client_sync(url=TURSO_DATABASE_URL, auth_token=TURSO_TOKEN)
    try:
        for item in items:
            sql = """
            INSERT INTO academic_pubs 
            (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(identifier) DO UPDATE SET 
                title=excluded.title, author=excluded.author, image=excluded.image;
            """
            client.execute(sql, [
                item["type"], item["title"], item["author"], item["publisher_journal"], 
                item["issue_volume"], item["identifier"], item["publish_date"], 
                item["abstract"], item["link"], item["image"]
            ])
    finally:
        client.close()

if __name__ == "__main__":
    all_records = []
    # Member ID 281 = MIT Press
    all_records.extend(fetch_from_crossref("281", "MIT Press"))
    # Member ID 73 = Duke University Press
    all_records.extend(fetch_from_crossref("73", "Duke University Press"))
    
    print(f"📥 總計取得 {len(all_records)} 筆資料，準備寫入...")
    save_to_db(all_records)
