import os
import re
import requests
import libsql_client
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================================
# 1. 取得環境變數
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# ==========================================
# 2. 爬蟲模組 A：Crossref API (適用 MIT & Duke)
# ==========================================
def fetch_from_crossref(member_id, publisher_name):
    print(f"🔍 [Crossref] 準備擷取 {publisher_name} 新書...")
    
    # 增加 monograph (專書) 類型，這是大學出版社最常用的新書格式
    types_to_fetch = ["book", "monograph"]
    headers = {"User-Agent": "BiblioappCloud/1.0 (mailto:admin@monoreader.cloud)"}
    all_items = []
    
    # 針對兩種書籍類型分別發送請求
    for t in types_to_fetch:
        url = f"https://api.crossref.org/members/{member_id}/works"
        params = {"filter": f"type:{t}", "sort": "published", "order": "desc", "rows": 15}
        try:
            res = requests.get(url, params=params, headers=headers, timeout=15)
            if res.status_code == 200:
                all_items.extend(res.json().get("message", {}).get("items", []))
        except Exception as e:
            print(f"⚠️ 取得 {t} 失敗: {e}")
            
    # 建立日期排序輔助函數
    def get_sort_date(item):
        # 優先讀取 issued (發行日)，其次為實體或線上出版日
        date_obj = item.get("issued") or item.get("published-print") or item.get("published-online") or {}
        parts = date_obj.get("date-parts", [[0]])[0]
        year = parts[0] if len(parts) > 0 and parts[0] else 0
        month = parts[1] if len(parts) > 1 and parts[1] else 1
        return (year, month)

    # 將抓回來的書目依照日期降冪排序，並取最新 20 筆
    all_items.sort(key=get_sort_date, reverse=True)
    top_items = all_items[:20]
    
    records = []
    for item in top_items:
        try:
            title = item.get("title", ["未命名書籍"])[0]
            authors_list = item.get("author", [])
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list]) or publisher_name
            
            # 安全提取出版日期
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
            
            # 分類邏輯 (若是ユリイカ或現代思想則為 Journal)
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
    all_records.extend(fetch_from_crossref("281", "MIT Press"))            # MIT Press
    all_records.extend(fetch_from_crossref("73", "Duke University Press")) # Duke Univ Press
    all_records.extend(crawl_seidosha())                                   # 青土社
    
    print(f"📥 總計取得 {len(all_records)} 筆資料，準備寫入資料庫...")
    save_to_db(all_records)
