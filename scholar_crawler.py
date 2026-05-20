import os
import re
import urllib.parse
import requests
import cloudscraper
import libsql_client
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================================
# 1. 取得環境變數
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# ==========================================
# 2. 具備防阻擋機制的 HTML 下載器
# ==========================================
def fetch_html_content(url):
    """
    先嘗試直連，若遇到 IP 封鎖 (HTTP 403)，自動切換至 AllOrigins 代理伺服器。
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }
    
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        res = scraper.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print(f"⚠️ 直連遭阻擋 ({e})，正在切換至代理伺服器模式...")
        
    try:
        print("🔄 透過 AllOrigins 繞過防火牆...")
        encoded_url = urllib.parse.quote(url)
        proxy_url = f"https://api.allorigins.win/raw?url={encoded_url}"
        
        res = requests.get(proxy_url, timeout=20)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print(f"❌ 代理伺服器亦無法取得資料: {e}")
        return None

# ==========================================
# 3. MIT Press 新書目錄專屬爬蟲
# ==========================================
def crawl_mit_press_new_releases():
    print("🔍 準備擷取 MIT Press 新書目錄 (New Releases)...")
    url = "https://mitpress.mit.edu/new-releases/"
    
    html_content = fetch_html_content(url)
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    # 尋找所有書籍的區塊
    book_blocks = soup.find_all("div", class_="book-wrapper")
    records = []
    
    print(f"📂 成功突破防火牆，找到 {len(book_blocks)} 本新書，開始解析...")

    for block in book_blocks:
        try:
            # --- 1. 提取標題與網址 ---
            title_tag = block.find("p", class_="sp__the-title")
            if not title_tag or not title_tag.find("a"): 
                continue
                
            a_tag = title_tag.find("a")
            title = a_tag.get_text(strip=True)
            raw_link = a_tag["href"]
            # MIT Press 的連結是相對路徑，需要補上網域
            link = f"https://mitpress.mit.edu{raw_link}" if raw_link.startswith("/") else raw_link
            
            # --- 2. 提取作者 ---
            author_tag = block.find("p", class_="sp__the-author")
            author = author_tag.get_text(strip=True) if author_tag else "MIT Press"
            
            # --- 3. 提取高畫質封面 ---
            img_tag = block.find("img", class_="lazyload")
            image_url = img_tag.get("data-src") if img_tag else None
            # 移除網址後方的縮圖參數 (?auto=format&w=145)，以取得原始大圖
            if image_url and "?" in image_url:
                image_url = image_url.split("?")[0]
                
            # --- 4. 提取 ISBN 作為唯一鍵 ---
            identifier = link
            isbn_match = re.search(r'/(\d{13})/', link)
            if isbn_match:
                identifier = isbn_match.group(1)

            records.append({
                "type": "Book",
                "title": title,
                "author": author,
                "publisher_journal": "MIT Press",
                "issue_volume": "",
                "identifier": identifier,
                "publish_date": datetime.utcnow().strftime("%Y-%m"), # 目錄頁無精準出版日，紀錄擷取月份
                "abstract": "（此來源僅提供新書目錄，無詳細摘要）", # 為了效率，不進行二次點擊
                "link": link,
                "image": image_url
            })
        except Exception as e:
            print(f"⚠️ 解析單本書籍時發生錯誤，略過: {e}")
            
    return records

# ==========================================
# 4. 寫入 Turso 資料庫 (Upsert)
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
                image=excluded.image;
            """
            client.execute(sql, [
                item["type"], item["title"], item["author"], item["publisher_journal"], 
                item["issue_volume"], item["identifier"], item["publish_date"], 
                item["abstract"], item["link"], item["image"]
            ])
            success_count += 1
        print(f"✅ 成功處理與寫入 {success_count} 筆 MIT Press 新書！")
    except Exception as e:
        print(f"❌ 寫入資料庫時發生錯誤: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    books = crawl_mit_press_new_releases()
    if books:
        print(f"📥 準備將 {len(books)} 筆資料寫入資料庫...")
        save_to_db(books)
    else:
        print("⚠️ 未解析到任何書籍。")
