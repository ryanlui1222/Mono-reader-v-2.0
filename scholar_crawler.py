import os
import feedparser
import libsql_client
from bs4 import BeautifulSoup

# ==========================================
# 1. 取得環境變數 (支援 GitHub Actions 傳入)
# ==========================================
# 為了相容性，同時支援 TURSO_TOKEN 與 TURSO_AUTH_TOKEN 兩種命名
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

# ==========================================
# 2. 資料清洗與提取工具
# ==========================================
def clean_html(raw_html):
    """清洗 HTML 標籤，只保留純文字作為摘要"""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    return " ".join(soup.get_text(strip=True).split())

def extract_image(raw_html):
    """從 RSS 內容中提取 <img> 標籤的圖片網址"""
    if not raw_html:
        return None
    soup = BeautifulSoup(raw_html, "html.parser")
    img_tag = soup.find('img')
    if img_tag and img_tag.get('src'):
        return img_tag['src']
    return None

# ==========================================
# 3. MIT Press 專屬爬蟲 (書籍)
# ==========================================
def crawl_mit_press():
    print("🔍 準備擷取 MIT Press 新書 RSS...")
    feed_url = "https://mitpress.mit.edu/feed/"
    feed = feedparser.parse(feed_url)
    
    records = []
    for entry in feed.entries:
        # 兼容不同 RSS 格式對內文的標籤定義
        raw_content = ""
        if "content" in entry:
            raw_content = entry["content"][0]["value"]
        elif "summary" in entry:
            raw_content = entry["summary"]
            
        title = entry.get("title", "未命名標題")
        link = entry.get("link", "")
        pub_date = entry.get("published", "") # 發布日期
        
        abstract = clean_html(raw_content)
        image_url = extract_image(raw_content)
        
        # 使用文章的 ID 或網址作為防重複寫入的 Unique Key
        identifier = entry.get("id", link)

        records.append({
            "type": "Book",
            "title": title,
            "author": entry.get("author", "MIT Press"), 
            "publisher_journal": "MIT Press",
            "issue_volume": "",
            "identifier": identifier,
            "publish_date": pub_date,
            "abstract": abstract[:600] + "..." if len(abstract) > 600 else abstract,
            "link": link,
            "image": image_url
        })
        
    return records

# ==========================================
# 4. 寫入 Turso 資料庫 (防重複更新)
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
        print(f"📥 成功解析到 {len(books)} 筆新書，準備寫入資料庫...")
        save_to_db(books)
    else:
        print("⚠️ 未解析到任何書籍。")
