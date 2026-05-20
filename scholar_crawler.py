import os
import re
import requests
import libsql_client

# ==========================================
# 1. 取得環境變數
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# ==========================================
# 2. Crossref API 官方授權爬蟲
# ==========================================
def crawl_mit_press_crossref():
    print("🔍 準備透過 Crossref API 擷取 MIT Press 新書...")
    
    # MIT Press 在 Crossref 的專屬 Member ID 是 281
    url = "https://api.crossref.org/members/281/works"
    
    # 設定檢索參數：過濾出「書籍 (book)」，並依據出版時間「降冪 (desc)」排序，抓取最新 20 筆
    params = {
        "filter": "type:book",
        "sort": "published",
        "order": "desc",
        "rows": 20
    }
    
    # 宣告 User-Agent (進入 Crossref 的 Polite Pool 禮貌通道，加速回應)
    headers = {
        "User-Agent": "BiblioappCloud/1.0 (mailto:admin@monoreader.cloud)"
    }
    
    records = []
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)
        res.raise_for_status()
        data = res.json()
        
        items = data.get("message", {}).get("items", [])
        print(f"📂 成功透過 API 取得 {len(items)} 筆 MIT Press 出版紀錄，開始解析 JSON...")
        
        for item in items:
            try:
                # 1. 標題
                title = item.get("title", ["未命名書籍"])[0]
                
                # 2. 作者群 (Crossref 提供陣列格式，自動組合名與姓)
                authors_list = item.get("author", [])
                author_names = []
                for a in authors_list:
                    given = a.get("given", "")
                    family = a.get("family", "")
                    author_names.append(f"{given} {family}".strip())
                author = ", ".join(author_names) if author_names else "MIT Press"
                
                # 3. 出版日期 (Crossref 的 date-parts 通常是 [YYYY, MM, DD])
                pub_date = "未知日期"
                date_parts = item.get("published", {}).get("date-parts", [[]])[0]
                if len(date_parts) >= 2:
                    pub_date = f"{date_parts[0]}-{date_parts[1]:02d}"
                elif len(date_parts) == 1:
                    pub_date = str(date_parts[0])
                    
                # 4. 識別碼 (優先使用 ISBN，去除橫線；若無則使用 DOI)
                doi = item.get("DOI", "")
                isbn_list = item.get("ISBN", [])
                isbn_raw = isbn_list[0] if isbn_list else ""
                isbn_clean = re.sub(r'[^0-9X]', '', str(isbn_raw))
                identifier = isbn_clean if isbn_clean else doi
                
                # 5. 永久連結 (優先使用 DOI Link)
                link = item.get("URL", f"https://doi.org/{doi}")
                
                # 6. 摘要 (Crossref 會帶有 <jats:p> 等 XML 標籤，需要正則清除)
                raw_abstract = item.get("abstract", "")
                abstract = re.sub(r'<[^>]+>', '', raw_abstract) if raw_abstract else "（官方暫無提供數位摘要）"
                
                # 7. 書封圖片 (利用 Open Library 的免費 API，根據 ISBN 自動獲取高畫質封面)
                # 若無 ISBN，則給予一張預設的佔位圖片
                if isbn_clean:
                    image_url = f"https://covers.openlibrary.org/b/isbn/{isbn_clean}-L.jpg"
                else:
                    image_url = "https://mitpress.mit.edu/wp-content/themes/university_press_theme/img/lazy-load-image.jpg"
                
                records.append({
                    "type": "Book",
                    "title": title,
                    "author": author,
                    "publisher_journal": "MIT Press",
                    "issue_volume": "",
                    "identifier": identifier,
                    "publish_date": pub_date,
                    "abstract": abstract[:600] + "..." if len(abstract) > 600 else abstract,
                    "link": link,
                    "image": image_url
                })
            except Exception as item_e:
                print(f"⚠️ 解析單筆 JSON 時發生錯誤: {item_e}")
                
    except Exception as e:
        print(f"❌ API 請求失敗: {e}")
        
    return records

# ==========================================
# 3. 寫入 Turso 資料庫 (防重複寫入)
# ==========================================
def save_to_db(items):
    if not TURSO_DATABASE_URL or not TURSO_TOKEN:
        print("❌ 錯誤：找不到 TURSO_DATABASE_URL 或 Token，請檢查環境變數。")
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
                title=excluded.title,
                author=excluded.author,
                abstract=excluded.abstract,
                image=excluded.image;
            """
            client.execute(sql, [
                item["type"], item["title"], item["author"], item["publisher_journal"], 
                item["issue_volume"], item["identifier"], item["publish_date"], 
                item["abstract"], item["link"], item["image"]
            ])
            success_count += 1
        print(f"✅ 成功處理與寫入 {success_count} 筆 MIT Press 書目！")
    except Exception as e:
        print(f"❌ 寫入資料庫時發生錯誤: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    books = crawl_mit_press_crossref()
    if books:
        print(f"📥 準備將 {len(books)} 筆資料寫入資料庫...")
        save_to_db(books)
    else:
        print("⚠️ 未解析到任何書籍。")
