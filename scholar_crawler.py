import os
import re
import cloudscraper
import feedparser
import libsql_client
from bs4 import BeautifulSoup

# ==========================================
# 1. 取得環境變數
# ==========================================
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# ==========================================
# 2. MIT Press 專屬爬蟲 (深度萃取)
# ==========================================
def crawl_mit_press():
    print("🔍 準備擷取 MIT Press 新書 RSS...")
    url = "https://mitpress.mit.edu/feed/"
    
    # 建立 cloudscraper 繞過 CloudFront 防火牆
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    
    try:
        res = scraper.get(url, timeout=15)
        res.raise_for_status()
    except Exception as e:
        print(f"❌ 無法下載 RSS 內容，可能遭到阻擋: {e}")
        return []

    # 使用 feedparser 解析我們抓下來的純文字 XML
    feed = feedparser.parse(res.text)
    records = []
    
    print(f"📂 成功取得 {len(feed.entries)} 篇書單/文章，正在深入解析書籍內容...")

    for entry in feed.entries:
        # 取得文章內的 HTML 結構
        html_content = ""
        if "content" in entry:
            html_content = entry["content"][0]["value"]
        elif "summary" in entry:
            html_content = entry["summary"]
            
        pub_date = entry.get("published", "")
        
        # 使用 BeautifulSoup 深度解析 HTML
        soup = BeautifulSoup(html_content, "html.parser")
        
        # MIT Press 將每本書放在這個特定的 div 區塊內
        book_blocks = soup.find_all("div", class_="wp-block-media-text")
        
        for block in book_blocks:
            try:
                # 1. 提取圖片網址
                img_tag = block.find("img")
                image_url = img_tag["src"] if img_tag else None
                
                # 2. 提取標題與網址
                h3_tag = block.find("h3")
                if not h3_tag: continue
                
                a_tag = h3_tag.find("a")
                link = a_tag["href"] if a_tag else ""
                title = a_tag.get_text(strip=True) if a_tag else "未命名書籍"
                
                # 3. 提取作者 (解析 "by Author Name" 的字串)
                h3_text = h3_tag.get_text(strip=True)
                author = "MIT Press"
                if " by " in h3_text:
                    author = h3_text.split(" by ")[-1].strip()
                    
                # 4. 提取摘要 (通常位於 h3 後面的段落)
                content_div = block.find("div", class_="wp-block-media-text__content")
                p_tags = content_div.find_all("p") if content_div else []
                abstract = " ".join([p.get_text(strip=True) for p in p_tags])
                
                # 5. 提取 ISBN 作為唯一識別碼 (從網址中尋找 13 碼數字)
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
                    "publish_date": pub_date,
                    "abstract": abstract[:600] + "..." if len(abstract) > 600 else abstract,
                    "link": link,
                    "image": image_url
                })
            except Exception as e:
                print(f"⚠️ 解析單本書籍時發生錯誤，略過: {e}")
                
    return records

# ==========================================
# 3. 寫入 Turso 資料庫 (防重複更新)
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
    books = crawl_mit_press()
    if books:
        print(f"📥 總共從文章中萃取出 {len(books)} 筆獨立書籍，準備寫入資料庫...")
        save_to_db(books)
    else:
        print("⚠️ 未解析到任何書籍。")
