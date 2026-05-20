import os
import re
import requests
import libsql_client
from bs4 import BeautifulSoup

# ==========================================
# 1. 取得環境變數
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# ==========================================
# 2. 爬蟲模組：MIT Press (Crossref API)
# ==========================================
def crawl_mit_press_crossref():
    print("🔍 [MIT Press] 準備透過 Crossref API 擷取...")
    url = "https://api.crossref.org/members/281/works"
    params = {"filter": "type:book", "sort": "published", "order": "desc", "rows": 15}
    headers = {"User-Agent": "BiblioappCloud/1.0"}
    
    records = []
    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)
        res.raise_for_status()
        items = res.json().get("message", {}).get("items", [])
        
        for item in items:
            title = item.get("title", ["未命名書籍"])[0]
            authors_list = item.get("author", [])
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list]) or "MIT Press"
            
            date_parts = item.get("published", {}).get("date-parts", [[]])[0]
            pub_date = f"{date_parts[0]}-{date_parts[1]:02d}" if len(date_parts) >= 2 else str(date_parts[0]) if date_parts else "未知日期"
            
            doi = item.get("DOI", "")
            isbn_list = item.get("ISBN", [])
            isbn_clean = re.sub(r'[^0-9X]', '', str(isbn_list[0])) if isbn_list else ""
            identifier = isbn_clean if isbn_clean else doi
            
            link = item.get("URL", f"https://doi.org/{doi}")
            raw_abstract = item.get("abstract", "")
            abstract = re.sub(r'<[^>]+>', '', raw_abstract) if raw_abstract else "（官方暫無提供數位摘要）"
            image_url = f"https://covers.openlibrary.org/b/isbn/{isbn_clean}-L.jpg" if isbn_clean else ""

            records.append({
                "type": "Book", "title": title, "author": author,
                "publisher_journal": "MIT Press", "issue_volume": "",
                "identifier": identifier, "publish_date": pub_date,
                "abstract": abstract[:600] + "..." if len(abstract) > 600 else abstract,
                "link": link, "image": image_url
            })
    except Exception as e:
        print(f"❌ [MIT Press] 擷取失敗: {e}")
    return records

# ==========================================
# 3. 爬蟲模組：青土社 (網頁 HTML 解析)
# ==========================================
def crawl_seidosha():
    print("🔍 [青土社] 準備擷取 新刊/雜誌...")
    url = "https://www.seidosha.co.jp/"
    records = []
    
    try:
        # 青土社網站沒有嚴格防禦，直接使用 requests 即可
        res = requests.get(url, timeout=15)
        res.encoding = 'utf-8' # 確保日文編碼正確
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 鎖定「新刊・雜誌」的區塊
        new_mag_section = soup.find("div", id="new_mag")
        if not new_mag_section:
            print("⚠️ [青土社] 找不到新刊區塊。")
            return records
            
        items = new_mag_section.find_all("div", class_="col-link-items")
        print(f"📂 [青土社] 發現 {len(items)} 筆新刊，開始解析...")
        
        for item in items:
            a_tag = item.find("a")
            if not a_tag: continue
            
            # 1. 連結
            raw_link = a_tag.get("href", "")
            link = f"https://www.seidosha.co.jp{raw_link.lstrip('.')}"
            
            # 2. 圖片 (包含 ISBN 檔名)
            img_tag = item.find("img")
            raw_img = img_tag.get("src", "") if img_tag else ""
            image_url = f"https://www.seidosha.co.jp{raw_img}" if raw_img else ""
            
            # 3. 提取 ISBN 作為 identifier
            identifier = link
            isbn_match = re.search(r'(\d{13})\.jpg', raw_img)
            if isbn_match:
                identifier = isbn_match.group(1)
                
            # 4. 標題與作者
            title_tag = item.find("h3", class_="h5")
            title = title_tag.get_text(strip=True) if title_tag else "未命名書籍"
            
            author_tag = item.find("p", class_="author")
            author = author_tag.get_text(strip=True) if author_tag else "青土社"
            
            # 5. 出版日期 (將 2026年5月27日 轉換為 2026-05-27)
            date_tag = item.find("p", class_="date")
            pub_date = date_tag.get_text(strip=True) if date_tag else ""
            pub_date = pub_date.replace("年", "-").replace("月", "-").replace("日", "")
            
            # 6. 分類邏輯 (若是雜誌則歸類為 Journal，否則為 Book)
            pub_type = "Journal" if "ユリイカ" in title or "現代思想" in title else "Book"
            
            records.append({
                "type": pub_type,
                "title": title,
                "author": author,
                "publisher_journal": "青土社",
                "issue_volume": "",
                "identifier": identifier,
                "publish_date": pub_date,
                "abstract": "（此為青土社新刊目錄擷取，無詳細摘要）",
                "link": link,
                "image": image_url
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
                title=excluded.title,
                author=excluded.author,
                publish_date=excluded.publish_date,
                image=excluded.image;
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
    
    # 執行 MIT Press 爬蟲
    mit_books = crawl_mit_press_crossref()
    all_records.extend(mit_books)
    
    # 執行青土社爬蟲
    seidosha_books = crawl_seidosha()
    all_records.extend(seidosha_books)
    
    print(f"📥 爬蟲執行完畢，總計取得 {len(all_records)} 筆資料，準備寫入資料庫...")
    save_to_db(all_records)
