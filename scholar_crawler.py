import os
import re
import requests
import cloudscraper
import base64
import libsql_client
import urllib.parse
import feedparser
from datetime import datetime
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

def crawl_urbanomic_forthcoming():
    """精準抓取 Urbanomic Forthcoming 區塊書籍"""
    print("🔍 [Urbanomic] 準備擷取 Forthcoming 書目...")
    url = "https://www.urbanomic.com/book/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    books = []
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        book_cards = soup.find_all('article') 
        
        for card in book_cards:
            text_content = card.get_text(separator=' ', strip=True).upper()
            if "FORTHCOMING" in text_content:
                title_tag = card.find(['h2', 'h3'])
                title = title_tag.get_text(strip=True) if title_tag else "未命名書籍"
                
                link_tag = card.find('a', href=True)
                link = link_tag['href'] if link_tag else url
                
                date_match = re.search(r'FORTHCOMING\s+([A-Z]{3}\s+\d{4})', text_content)
                pub_date = date_match.group(1) if date_match else "即將出版"
                
                # 擷取封面圖片 (若無則留空)
                img_tag = card.find('img')
                image_url = img_tag.get('src', '') if img_tag else ""
                
                books.append({
                    "type": "Book",
                    "title": title,
                    "author": "Urbanomic", 
                    "publisher_journal": "Urbanomic",
                    "identifier": link, # 🌟 補上 identifier，以網址作為唯一識別碼
                    "link": link,
                    "publish_date": pub_date,
                    "abstract": "（即將出版之前瞻書目）",
                    "image": image_url, # 🌟 補上 image 鍵值
                    "is_manual": 0,
                    "category": "學術專著"
                })
    except Exception as e:
        print(f"❌ Urbanomic 爬取失敗: {e}")
        
    return books

def crawl_utp():
    """精準抓取東京大学出版会新刊網頁"""
    print("🔍 [東京大学出版会] 準備擷取新刊清單...")
    url = "https://www.utp.or.jp/search/new.html"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    books = []
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 定位到書籍清單區塊
        book_list = soup.find('div', class_='booklist')
        if not book_list:
            return books
            
        items = book_list.find_all('div', class_='item')
        
        for item in items:
            # 1. 擷取標題與連結
            ttl_tag = item.find('div', class_='ttl').find('a')
            title = ttl_tag.get_text(strip=True) if ttl_tag else "未命名書籍"
            raw_link = ttl_tag['href'] if ttl_tag else ""
            link = f"https://www.utp.or.jp{raw_link}" if raw_link else url
            
            # 2. 擷取作者 (將多個作者/譯者透過空白組合，例如「塩野谷 祐一 著」)
            author_tag = item.find('div', class_='author')
            author = author_tag.get_text(separator=' ', strip=True) if author_tag else "東京大学出版会"
            
            # 3. 擷取封面圖片 (直接抓取 Amazon S3 上的圖檔網址)
            img_tag = item.find('div', class_='image').find('img')
            image_url = img_tag['src'] if img_tag else ""
            
            # 4. 自動判定文獻類型 (如果標題包含 "UP "，判定為雜誌/期刊)
            pub_type = "Journal" if "UP " in title else "Book"
            
            books.append({
                "type": pub_type,
                "title": title,
                "author": author,
                "publisher_journal": "東京大学出版会",
                "identifier": link, # 使用網址作為唯一識別碼
                "link": link,
                "publish_date": datetime.utcnow().strftime("%Y-%m"), # 列表頁無具體日期，預設寫入爬取當月
                "abstract": "（東京大学出版会新刊）",
                "image": image_url,
                "is_manual": 0,
                "category": "學術專著"
            })
    except Exception as e:
        print(f"❌ 東京大学出版会 爬取失敗: {e}")
        
    return books
    
def crawl_verso():
    """抓取 Verso Books Atom Feed"""
    print("🔍 [Verso Books] 準備擷取 Atom...")
    url = "https://www.versobooks.com/collections/catalog.atom"
    feed = feedparser.parse(url)
    books = []
    
    for entry in feed.entries:
        author = entry.author if 'author' in entry else "Verso Books"
        abstract_text = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:300]
        
        books.append({
            "type": "Book",
            "title": entry.title,
            "author": author,
            "publisher_journal": "Verso Books",
            "identifier": entry.link, # 🌟 補上 identifier
            "link": entry.link,
            "publish_date": entry.get("published", datetime.utcnow().strftime("%Y-%m-%d")),
            "abstract": abstract_text,
            "image": "", # 🌟 補上 image
            "is_manual": 0,
            "category": "學術專著"
        })
    return books
    
# ==========================================
# 重構：青土社精細化目錄爬蟲 (支援《現代思想》與《ユリイカ》單篇萃取與分家)
# ==========================================
def crawl_seidosha():
    print("🔍 [青土社] 準備擷取單期目錄...")
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
            
            issue_title = item.find("h3", class_="h5").get_text(strip=True)
            img_src = item.find("img").get("src", "")
            image_url = f"https://www.seidosha.co.jp{img_src}"
            
            # 🌟 精準分離期刊名稱
            journal_name = ""
            if "ユリイカ" in issue_title: journal_name = "ユリイカ"
            elif "現代思想" in issue_title: journal_name = "現代思想"
            
            is_journal = bool(journal_name)
            
            if is_journal:
                try:
                    inner_res = requests.get(link, timeout=15)
                    inner_res.encoding = 'utf-8'
                    inner_soup = BeautifulSoup(inner_res.text, "html.parser")
                    
                    # 🌟 鎖定內文區塊，排除上方定價與 ISBN 的 div
                    info_area = inner_soup.find("div", class_="book-info-text")
                    if info_area:
                        lines = info_area.get_text(separator='\n').split('\n')
                        article_count = 0
                        for line in lines:
                            clean_line = line.strip()
                            
                            # 🌟 嚴格過濾：必須包含全形斜線才視為目錄條目
                            if '／' in clean_line:
                                parts = clean_line.split('／')
                                article_title = parts[0].strip()
                                article_author = parts[1].strip() if len(parts) > 1 else "未知作者"
                                
                                article_count += 1
                                records.append({
                                    "type": "Journal",
                                    "title": article_title,
                                    "author": article_author,
                                    "publisher_journal": journal_name, # 寫入獨立的期刊名稱
                                    "issue_volume": issue_title, 
                                    "identifier": f"{link}_art_{article_count}",
                                    "publish_date": datetime.utcnow().strftime("%Y-%m-%d"),
                                    "abstract": "（青土社單篇論文）",
                                    "link": link,
                                    "image": image_url
                                })
                        if article_count > 0:
                            continue 
                except Exception as e:
                    print(f"⚠️ 青土社目錄擷取失敗，退回整本記錄模式: {e}")

            # 備用方案
            id_match = re.search(r'id=(\d+)', link)
            identifier = f"seidosha_{id_match.group(1)}" if id_match else link
            records.append({
                "type": "Journal" if is_journal else "Book",
                "title": issue_title, 
                "author": item.find("p", class_="author").get_text(strip=True) or "青土社",
                "publisher_journal": journal_name if is_journal else "青土社", 
                "issue_volume": issue_title if is_journal else "", 
                "identifier": identifier, 
                "publish_date": datetime.utcnow().strftime("%Y-%m-%d"), 
                "abstract": "（青土社新刊）", 
                "link": link, 
                "image": image_url
            })
        return records
    except Exception as e: 
        print(f"❌ [青土社] 錯誤: {e}")
        return []        
# ==========================================
# 新增：期刊專用 Crossref API 擷取器
# ==========================================
def fetch_journal_from_crossref(issn, journal_name):
    print(f"🔍 [Crossref] 正在擷取期刊 {journal_name} 最新一期...")
    url = f"https://api.crossref.org/journals/{issn}/works"
    # 將 rows 拉高以確保能完整覆蓋一整期的文章數量
    params = {"sort": "published", "order": "desc", "rows": 100}
    headers = {"User-Agent": "BiblioappCloud/1.0"}
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=15)
        items = res.json().get("message", {}).get("items", [])
        if not items: return []
        
        # 1. 確立最新期號基準
        latest_item = items[0]
        target_issue = latest_item.get("issue", "")
        target_volume = latest_item.get("volume", "")
        
        date_obj = latest_item.get("issued") or latest_item.get("published-print") or latest_item.get("published-online") or {}
        date_parts = date_obj.get("date-parts", [[]])[0]
        target_ym = f"{date_parts[0]}-{date_parts[1]:02d}" if len(date_parts) >= 2 else str(date_parts[0]) if date_parts else ""

        records = []
        for item in items:
            # 2. 獲取當前迴圈文章的期號資訊
            curr_issue = item.get("issue", "")
            curr_vol = item.get("volume", "")
            
            c_date_obj = item.get("issued") or item.get("published-print") or item.get("published-online") or {}
            c_date_parts = c_date_obj.get("date-parts", [[]])[0]
            curr_ym = f"{c_date_parts[0]}-{c_date_parts[1]:02d}" if len(c_date_parts) >= 2 else str(c_date_parts[0]) if c_date_parts else ""

            # 3. 嚴格過濾：有期號則比對期號與卷號，無期號則比對出版年月
            is_same_issue = False
            if target_issue:
                if curr_issue == target_issue and curr_vol == target_volume: is_same_issue = True
            else:
                if curr_ym == target_ym: is_same_issue = True
            
            if not is_same_issue: continue # 剔除不屬於最新期的舊文章

            title = item.get("title", ["未命名論文"])[0]
            authors_list = item.get("author", [])
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list]) or journal_name
            
            # 組合前端顯示用的期號文字
            issue_display = f"Vol. {curr_vol}, Issue {curr_issue}" if curr_vol and curr_issue else (f"Issue {curr_issue}" if curr_issue else curr_ym)
            link = item.get("URL", f"https://doi.org/{item.get('DOI', '')}")
            
            records.append({
                "type": "Journal", "title": title, "author": author, "publisher_journal": journal_name, "issue_volume": issue_display,
                "identifier": item.get("DOI", link), "publish_date": curr_ym, "abstract": "（API 期刊論文擷取）", "link": link, "image": ""
            })
        return records
    except Exception as e:
        print(f"❌ [{journal_name}] 擷取失敗: {e}")
        return []
        
def save_to_db(items):
    client = libsql_client.create_client_sync(url=TURSO_DATABASE_URL, auth_token=TURSO_TOKEN)
    for item in items:
        # 補上 category 預設值
        cat = item.get("category", "未分類")
        
        # 🌟 修改 SQL：寫入 category，但 ON CONFLICT 不更新 category，防護手動修改
        sql = """INSERT INTO academic_pubs (type, title, author, publisher_journal, identifier, publish_date, abstract, link, image, category)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                 ON CONFLICT(identifier) DO UPDATE SET image=excluded.image, title=excluded.title;"""
                 
        client.execute(sql, [item["type"], item["title"], item["author"], item["publisher_journal"], 
                             item["identifier"], item["publish_date"], item["abstract"], item["link"], item["image"], cat])
    client.close()
    print("✅ 資料庫更新完成。")

# ==========================================
# 於主程式執行區段註冊所有期刊
# ==========================================
if __name__ == "__main__":
    all_books = []
    
    # 既有專書來源
    all_books.extend(fetch_from_crossref("281", "MIT Press"))
    all_books.extend(fetch_from_crossref("73", "Duke University Press"))
    all_books.extend(crawl_utp())
    all_books.extend(crawl_verso())
    all_books.extend(crawl_urbanomic_forthcoming())
    all_books.extend(crawl_seidosha())
    
    # 新增學術期刊追蹤清單
    all_books.extend(fetch_journal_from_crossref("2578-3491", "PRISM: Theory and Modern Chinese Literature"))
    all_books.extend(fetch_journal_from_crossref("2201-1919", "Environmental Humanities"))
    all_books.extend(fetch_journal_from_crossref("1067-9847", "positions: asia critique"))
    all_books.extend(fetch_journal_from_crossref("0091-7729", "Science Fiction Studies"))
    all_books.extend(fetch_journal_from_crossref("2768-3532", "Chinese literature and thought today"))
    all_books.extend(fetch_journal_from_crossref("0190-3659", "boundary 2"))
    all_books.extend(fetch_journal_from_crossref("1520-9857", "MCLC (Modern Chinese Literature and Culture)"))
    all_books.extend(fetch_journal_from_crossref("1076-0962", "ISLE: Interdisciplinary Studies in Literature and Environment"))
    all_books.extend(fetch_journal_from_crossref("2405-6472", "Journal of World Literature (JWL)"))
    all_books.extend(fetch_journal_from_crossref("0010-4132", "Comparative Literature Studies (CLS)"))
    
    save_to_db(all_books)
