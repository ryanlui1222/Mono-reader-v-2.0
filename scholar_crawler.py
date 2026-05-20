import os
import re
import urllib.parse
import requests
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
# 2. 具備防阻擋機制的下載器 (WAF Bypass)
# ==========================================
def fetch_xml_content(url):
    """
    先嘗試模擬瀏覽器直連，若遇到 IP 封鎖 (如 GitHub Actions)，
    則自動切換至公開的 AllOrigins 代理伺服器繞過防火牆。
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9'
    }
    
    # 策略 A：使用 Cloudscraper 直連 (適用於您的本地電腦)
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        res = scraper.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print(f"⚠️ 直連遭阻擋 ({e})，正在切換至代理伺服器模式...")
        
    # 策略 B：透過 AllOrigins 代理伺服器抓取 (專門用來拯救 GitHub Actions)
    try:
        print("🔄 透過 AllOrigins 繞過 AWS CloudFront 防火牆...")
        encoded_url = urllib.parse.quote(url)
        # 使用 /raw 端點，直接取得原始的 XML 文字
        proxy_url = f"https://api.allorigins.win/raw?url={encoded_url}"
        
        res = requests.get(proxy_url, timeout=20)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print(f"❌ 代理伺服器亦無法取得資料: {e}")
        return None

# ==========================================
# 3. MIT Press 專屬爬蟲 (深度萃取)
# ==========================================
def crawl_mit_press():
    print("🔍 準備擷取 MIT Press 新書 RSS...")
    feed_url = "https://mitpress.mit.edu/feed/"
    
    # 取得原始 XML
    xml_content = fetch_xml_content(feed_url)
    if not xml_content:
        return []

    # 使用 feedparser 解析字串
    feed = feedparser.parse(xml_content)
    records = []
    
    print(f"📂 成功突破防火牆，取得 {len(feed.entries)} 篇書單/文章，正在深入解析書籍內容...")

    for entry in feed.entries:
        # 取得文章內的 HTML 結構
        html_content = ""
        if "content" in entry:
            html_content = entry["content"][0]["value"]
        elif "summary" in entry:
            html_content = entry["summary"]
            
        pub_date = entry.get("published", "")
        
        # 使用 BeautifulSoup 深度解析 HTML 以萃取單本書籍
        soup = BeautifulSoup(html_content, "html.parser")
        book_blocks = soup.find_all("div", class_="wp-block-media-text")
        
        for block in book_blocks:
            try:
                img_tag = block.find("img")
                image_url = img_tag["src"] if img_tag else None
                
                h3_tag = block.find("h3")
                if not h3_tag: continue
                
                a_tag = h3_tag.find("a")
                link = a_tag["href"] if a_tag else ""
                title = a_tag.get_text(strip=True) if a_tag else "未命名書籍"
                
                h3_text = h3_tag.get_text(strip=True)
                author = "MIT Press"
                if " by " in h3_text:
                    author = h3_text.split(" by ")[-1].strip()
                    
                content_div = block.find("div", class_="wp-block-media-text__content")
                p_tags = content_div.find_all("p") if content_div else []
                abstract = " ".join([p.get_text(strip=True) for p in p_tags])
                
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
        print(f"📥 總共從文章中萃取出 {len(books)} 筆獨立書籍，準備寫入資料庫...")
        save_to_db(books)
    else:
        print("⚠️ 未解析到任何書籍。")
