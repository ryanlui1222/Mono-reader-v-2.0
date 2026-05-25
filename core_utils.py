import streamlit as st
import pandas as pd
import libsql_client
import math
import re
import requests
import cloudscraper
import base64
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

SOURCE_URLS = {
    "Aeon 思想誌": "https://aeon.co/", "New Yorker, Books and Culture": "https://www.newyorker.com/culture",
    "421 News (EN)": "https://www.421.news/en", "421 News (ZH)": "https://www.421.news/zh",
    "聯經思想空間": "https://www.linking.vision/", "上海書評": "https://www.thepaper.cn/list_25444",
    "藝術界": "https://www.leapleapleap.com/", "MIT Press Reader": "https://thereader.mitpress.mit.edu/",
    "webゲンロン": "https://webgenron.com/", "e-flux Journal": "https://www.e-flux.com/journal/",
    "Eurozine": "https://www.eurozine.com/essays/", "美術手帖": "https://bijutsutecho.com/magazine/series",
    "澎湃思想市場": "https://www.thepaper.cn/list_25483", "Verso Blog": "https://www.versobooks.com/blogs/news",
    "The Point": "https://thepointmag.com/magazine/", "The Funambulist": "https://thefunambulist.net/",
    "BIE別的": "https://www.biede.com/", "Sabukaru": "https://sabukaru.online/articles", 
    "TripleAmpersand": "https://tripleampersand.org/", "WIRED.jp": "https://wired.jp/",
    "CINRA": "https://www.cinra.net/", "VERSE": "https://www.verse.com.tw/",
    "界面文化": "https://www.jiemian.com/lists/130.html", "Radii": "https://radii.co/",
    "Duke Press": "https://dukeupress.wordpress.com/",
    "Asian Review of Books": "https://asianreviewofbooks.com/",
    "The Comics Journal": "https://www.tcj.com/", "FNMNL": "https://fnmnl.tv/",
    "触乐": "https://www.chuapp.com/tag/index/id/20369.html",
    "MCLC Resource Center": "https://u.osu.edu/mclc/list/blog/",
    "结绳志": "https://tyingknots.net/"
}
FAST_NEWS_SOURCES = ["WIRED.jp", "CINRA", "VERSE", "界面文化", "Radii", "触乐", "FNMNL"]

def get_source_link(source_name): return SOURCE_URLS.get(source_name.split(" (")[0], "#")

@st.cache_resource
def init_connection(): return libsql_client.create_client_sync(url=st.secrets["TURSO_DATABASE_URL"], auth_token=st.secrets["TURSO_AUTH_TOKEN"])
db = init_connection()

@st.cache_data(ttl=600)
def fetch_data(view_mode, source_filter="全部來源總覽", search_query=""):
    sql, args = "SELECT * FROM articles WHERE 1=1", []
    if search_query:
        sql += " AND (Title LIKE ? OR Summary LIKE ?)"; args.extend([f"%{search_query}%", f"%{search_query}%"])
        if view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽": sql += " AND Source = ?"; args.append(source_filter)
        elif view_mode == "🔖 我的收藏庫": sql += " AND is_bookmarked = 1"
    else:
        if view_mode in ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊"]: sql += " AND SortDate >= ?"; args.append((datetime.utcnow() - timedelta(hours=24)).isoformat())
        elif view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽": sql += " AND Source = ?"; args.append(source_filter)
        elif view_mode == "🔖 我的收藏庫": sql += " AND is_bookmarked = 1"
    sql += " ORDER BY SortDate DESC LIMIT 500"
    res = db.execute(sql, args)
    if not res.rows: return pd.DataFrame()
    df = pd.DataFrame([dict(zip(res.columns, row)) for row in res.rows])
    if view_mode == "✍️ 最新評論": df = df[~df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)]
    elif view_mode == "⚡ 文化快訊": df = df[df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)]
    return df

@st.cache_data(ttl=600)
def fetch_academic_pubs(view_mode="探索", pub_type="Book", source_filter="總覽", search_query=""):
    sql, args = "SELECT * FROM academic_pubs WHERE 1=1", []
    
    # 🌟 處理全域搜尋：若有輸入字串，對多個欄位進行模糊比對
    if search_query:
        sql += " AND (title LIKE ? OR author LIKE ? OR abstract LIKE ? OR publisher_journal LIKE ?)"
        like_term = f"%{search_query}%"
        args.extend([like_term, like_term, like_term, like_term])
        
    if view_mode == "🔖 待讀書架":
        sql += " AND is_bookmarked = 1 AND type != 'Web Link'"
    elif view_mode == "🔗 網址備存":
        sql += " AND type = 'Web Link'"
    else:
        sql += " AND type = ?"; args.append(pub_type)
        
        if source_filter == "手動加入":
            sql += " AND is_manual = 1"
        elif source_filter != "總覽 (依日期遞減)": 
            sql += " AND publisher_journal = ?"; args.append(source_filter)
            
    sql += " ORDER BY publish_date DESC LIMIT 500"
    res = db.execute(sql, args)
    if not res.rows: return pd.DataFrame()
    return pd.DataFrame([dict(zip(res.columns, row)) for row in res.rows])

def toggle_bookmark_db(link, current_state):
    try: db.execute("UPDATE articles SET is_bookmarked = ? WHERE Link = ?", [0 if current_state else 1, link]); st.cache_data.clear(); st.toast("書籤更新！")
    except Exception as e: st.error(f"操作失敗: {e}")

def delete_article_db(link):
    try: db.execute("DELETE FROM articles WHERE Link = ?", [link]); st.cache_data.clear(); st.toast("🗑️ 文章已抹除！")
    except Exception as e: st.error(f"刪除失敗: {e}")

def toggle_biblio_bookmark_db(pub_id, current_state):
    try: db.execute("UPDATE academic_pubs SET is_bookmarked = ? WHERE id = ?", [0 if current_state else 1, pub_id]); st.cache_data.clear(); st.toast("書架狀態更新！")
    except Exception as e: st.error(f"操作失敗: {e}")

def delete_biblio_db(pub_id):
    try: db.execute("DELETE FROM academic_pubs WHERE id = ?", [pub_id]); st.cache_data.clear(); st.toast("🗑️ 紀錄已徹底刪除！")
    except Exception as e: st.error(f"刪除失敗: {e}")

def fetch_custom_resources(module_name):
    res = db.execute("SELECT * FROM custom_resources WHERE module = ? ORDER BY added_date DESC", [module_name])
    return pd.DataFrame([dict(zip(res.columns, row)) for row in res.rows]) if res.rows else pd.DataFrame()

def add_custom_resource(module_name, url):
    if not url.startswith("http"): return False, "⚠️ 請輸入完整的網址 (包含 http)"
    title = "未命名網站"
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        res = scraper.get(url, timeout=15)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            if soup.find('meta', property='og:title'): 
                title = soup.find('meta', property='og:title').get('content')
            elif soup.find('meta', attrs={'name': 'twitter:title'}): 
                title = soup.find('meta', attrs={'name': 'twitter:title'}).get('content')
            elif soup.find('title'): 
                title = soup.find('title').get_text()
            if title and title != "未命名網站":
                title = title.split('|')[0].split(' - ')[0].strip()
            else:
                title = "未命名網站"
    except Exception as e:
        print(f"⚠️ 標題擷取失敗 ({e})，轉為手動命名模式。")
    try:
        db.execute("INSERT INTO custom_resources (module, title, url, added_date) VALUES (?, ?, ?, ?) ON CONFLICT(url) DO UPDATE SET title=excluded.title", 
                   [module_name, title, url, datetime.utcnow().isoformat()])
        st.cache_data.clear()
        return True, f"✅ 已成功加入清單！(若名稱不如預期，請點擊右側管理修改)"
    except Exception as e:
        return False, f"❌ 資料庫寫入錯誤: {e}"

def update_custom_resource(res_id, new_title, new_comment=""):
    try:
        db.execute("UPDATE custom_resources SET title = ?, comment = ? WHERE id = ?", [new_title, new_comment, res_id])
        st.cache_data.clear(); st.toast("✏️ 網站資訊與備註已更新！")
    except Exception as e: st.error(f"更新失敗: {e}")

def delete_custom_resource(res_id):
    try:
        db.execute("DELETE FROM custom_resources WHERE id = ?", [res_id])
        st.cache_data.clear(); st.toast("🗑️ 網站已從清單中移除！")
    except Exception as e: st.error(f"刪除失敗: {e}")

def get_secure_image_base64(img_url, source=""):
    if not img_url: return ""
    if str(img_url).startswith("data:image"): return img_url
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        headers = {"User-Agent": "Mozilla/5.0"}
        if source == "douban": headers["Referer"] = "https://book.douban.com/"
        res = scraper.get(img_url, headers=headers, timeout=10)
        if res.status_code == 200 and len(res.content) > 500:
            return f"data:{res.headers.get('Content-Type', 'image/jpeg')};base64,{base64.b64encode(res.content).decode('utf-8')}"
    except: pass
    return img_url

def fetch_google_fallback(isbn):
    try:
        res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}", timeout=5).json()
        if "items" in res and len(res["items"]) > 0:
            info = res["items"][0].get("volumeInfo", {})
            img = info.get("imageLinks", {}).get("thumbnail", "").replace("http://", "https://")
            return {
                "type": "Book", "title": info.get("title", "未命名書籍"), "author": ", ".join(info.get("authors", [])),
                "publisher_journal": info.get("publisher", "手動加入"), "issue_volume": "", "identifier": isbn, 
                "publish_date": info.get("publishedDate", datetime.utcnow().strftime("%Y-%m-%d")),
                "abstract": info.get("description", "（無摘要）")[:600], "link": info.get("infoLink", ""),
                "image": get_secure_image_base64(img, "google"), "is_bookmarked": 0
            }
    except: pass
    return None

def fetch_openbd(isbn):
    try:
        res = requests.get(f"https://api.openbd.jp/v1/get?isbn={isbn}", timeout=10).json()
        if res and res[0]:
            info = res[0].get("summary", {})
            img_url = get_secure_image_base64(info.get("cover", ""), "openbd") if info.get("cover") else get_secure_image_base64(f"https://www.hanmoto.com/bd/img/{isbn}.jpg", "hanmoto")
            return {
                "type": "Book", "title": info.get("title", "未命名"), "author": info.get("author", "未知"),
                "publisher_journal": info.get("publisher", "手動加入"), "issue_volume": "", "identifier": isbn, 
                "publish_date": info.get("pubdate", datetime.utcnow().strftime("%Y-%m-%d")), "abstract": "（日文出版品）",
                "link": f"https://ndlsearch.ndl.go.jp/books/R100000002-I{isbn}", "image": img_url, "is_bookmarked": 0
            }
    except: pass
    return fetch_google_fallback(isbn)

def fetch_douban(isbn):
    url = f"https://book.douban.com/isbn/{isbn}/"
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        res = scraper.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            title = soup.find("span", property="v:itemreviewed").text.strip() if soup.find("span", property="v:itemreviewed") else "未知"
            mainpic = soup.find("div", id="mainpic")
            img_url = get_secure_image_base64(mainpic.find("img").get("src", "").replace("/s/public/", "/l/public/"), "douban") if mainpic and mainpic.find("img") else ""
            author_span = soup.find("span", string=re.compile("作者"))
            author = author_span.find_next("a").text.strip() if author_span and author_span.find_next("a") else "未知"
            pub_span = soup.find("span", string=re.compile("出版社"))
            publisher = pub_span.next_sibling.strip().replace(":", "").strip() if pub_span and pub_span.next_sibling else "手動加入"
            intro = soup.find("div", class_="intro")
            abstract = intro.text.strip().replace("\n", " ") if intro else "（無摘要）"
            return {
                "type": "Book", "title": title, "author": author, "publisher_journal": publisher, "issue_volume": "", 
                "identifier": isbn, "publish_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "abstract": abstract[:600], "link": url, "image": img_url, "is_bookmarked": 0
            }
    except: pass
    return fetch_google_fallback(isbn)

def fetch_book_by_isbn(isbn):
    clean_isbn = re.sub(r'[^0-9X]', '', str(isbn).upper())
    if not clean_isbn: return None
    if clean_isbn.startswith("9784") or clean_isbn.startswith("9794"): return fetch_openbd(clean_isbn)
    elif clean_isbn.startswith("9787") or clean_isbn.startswith("978957") or clean_isbn.startswith("978986") or clean_isbn.startswith("978626"): return fetch_douban(clean_isbn)
    
    best_cover = ""
    try:
        syn_res = requests.get(f"https://syndetics.com/index.aspx?isbn={clean_isbn}/lc.jpg&client=test", timeout=5)
        if syn_res.status_code == 200 and len(syn_res.content) > 100: best_cover = f"https://syndetics.com/index.aspx?isbn={clean_isbn}/lc.jpg&client=test"
    except: pass

    res = fetch_google_fallback(clean_isbn)
    if res:
        if best_cover: res["image"] = best_cover
        return res
        
    try:
        ol_data = requests.get(f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean_isbn}&format=json&jscmd=data", timeout=5).json()
        if f"ISBN:{clean_isbn}" in ol_data:
            info = ol_data[f"ISBN:{clean_isbn}"]
            authors = [a.get("name", "") for a in info.get("authors", [])]
            return {
                "type": "Book", "title": info.get("title", "未命名"), "author": ", ".join(authors) or "未知",
                "publisher_journal": info.get("publishers", [{"name": "手動加入"}])[0].get("name", "手動加入"), "issue_volume": "",
                "identifier": clean_isbn, "publish_date": info.get("publish_date", datetime.utcnow().strftime("%Y-%m-%d")),
                "abstract": "（Open Library 匯入）", "link": info.get("url", ""), 
                "image": best_cover if best_cover else info.get("cover", {}).get("large", f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"), "is_bookmarked": 0
            }
    except: pass
    return None

def fetch_book_by_url(url):
    if not url.startswith("http"): return None
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    try:
        res = scraper.get(url, timeout=15)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            og_title = soup.find('meta', property='og:title')
            title = og_title['content'] if og_title and og_title.get('content') else (soup.find('title').get_text() if soup.find('title') else '未命名書籍')
            title = title.split('|')[0].split(' - ')[0].replace('Amazon.co.jp:', '').replace('Amazon.com:', '').strip()
            
            og_img = soup.find('meta', property='og:image')
            img_url = og_img['content'] if og_img and og_img.get('content') else ""
            if img_url: img_url = get_secure_image_base64(img_url, "url_backup")
            
            author_meta = soup.find('meta', attrs={'name': 'author'}) or soup.find('meta', property='article:author')
            author = author_meta['content'] if author_meta and author_meta.get('content') else ""
            if not author:
                for p in soup.find_all(['p', 'span', 'a'], class_=re.compile(r'author|byline', re.I)):
                    p_text = p.get_text(strip=True)
                    if p_text and len(p_text) < 50:
                        author = p_text
                        break
            if not author: author = "未知作者"
            
            og_desc = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'description'})
            abstract = og_desc['content'] if og_desc and og_desc.get('content') else ""
            
            url_hash = f"url_{id(url)}"
            match = re.search(r'dp/([A-Z0-9]{10})|product/([A-Z0-9]{10})|asin/([A-Z0-9]{10})', url, re.I)
            if match: url_hash = f"amazon_{match.group(1) or match.group(2) or match.group(3)}"

            return {
                "type": "Web Link", "title": title, "author": author, "publisher_journal": "網頁備存", 
                "issue_volume": "", "identifier": url_hash, "publish_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "abstract": abstract[:600] if abstract else "（透過外部網址備存導入）", "link": url, 
                "image": img_url, "is_bookmarked": 0
            }
    except Exception as e:
        print(f"網址備存解析失敗: {e}")
    return None
    
def fetch_external_article(url):
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    try:
        res = scraper.get(url, timeout=15)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        og_title = soup.find('meta', property='og:title')
        title = og_title['content'] if og_title and og_title.get('content') else (soup.find('title').get_text() if soup.find('title') else '未知標題')
        og_img = soup.find('meta', property='og:image')
        img_url = og_img['content'] if og_img and og_img.get('content') else None
        author_meta = soup.find('meta', attrs={'name': 'author'}) or soup.find('meta', property='article:author')
        author = author_meta['content'] if author_meta and author_meta.get('content') else ""
        og_desc = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'description'})
        summary = og_desc['content'] if og_desc and og_desc.get('content') else ""
        if not summary or len(summary) < 20:
            paragraphs = [p.get_text(strip=True) for p in soup.find_all('p') if len(p.get_text(strip=True)) > 30]
            summary = " ".join(paragraphs[:3]) if paragraphs else "（無法自動擷取摘要文字）"
        final_summary = f"**👤 著者：** {author}\n\n{summary}" if author else summary
        if len(final_summary) > 400: final_summary = final_summary[:400] + "..."
        return {"Source": "🌐 外部手動匯入", "Title": title.strip(), "Link": url, "Published": "手動收藏", "Summary": final_summary, "Image": img_url, "SortDate": datetime.utcnow().isoformat(), "is_bookmarked": 1}
    except: return None

# ==========================================
# 參考書目與註釋管理模組 (Bibliography)
# ==========================================
def init_bibliography_table():
    """初始化參考書目專用資料表"""
    try:
        db.execute("""
        CREATE TABLE IF NOT EXISTS bibliography_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier TEXT UNIQUE,
            type TEXT,
            title TEXT,
            author TEXT,
            publisher_journal TEXT,
            issue_volume TEXT,
            publish_date TEXT,
            importance TEXT,
            notes TEXT,
            link TEXT,
            added_date TEXT
        )
        """)
    except Exception as e:
        print(f"初始化參考書目表失敗: {e}")

# 啟動時自動檢查建表
init_bibliography_table()

def fetch_doi_metadata(doi):
    clean_doi = doi.replace("https://doi.org/", "").strip()
    url = f"https://api.crossref.org/works/{clean_doi}"
    try:
        res = requests.get(url, headers={"User-Agent": "BiblioappCloud/1.0"}, timeout=10)
        if res.status_code == 200:
            item = res.json().get("message", {})
            title = item.get("title", ["未命名文獻"])[0]
            authors_list = item.get("author", [])
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_list])
            
            container = item.get("container-title", [""])[0]
            publisher = item.get("publisher", "")
            pub_journal = container if container else publisher
            
            vol = item.get("volume", "")
            iss = item.get("issue", "")
            issue_vol = f"Vol. {vol}, Issue {iss}" if vol and iss else (f"Issue {iss}" if iss else "")
            
            date_obj = item.get("issued") or item.get("published-print") or item.get("published-online") or {}
            date_parts = date_obj.get("date-parts", [[]])[0]
            pub_date = f"{date_parts[0]}-{date_parts[1]:02d}" if len(date_parts) >= 2 else str(date_parts[0]) if date_parts else "未知日期"
            
            link = item.get("URL", f"https://doi.org/{clean_doi}")
            
            return {
                "type": "Journal" if container else "Book",
                "title": title, "author": author, "publisher_journal": pub_journal,
                "issue_volume": issue_vol, "identifier": clean_doi, "publish_date": pub_date,
                "link": link
            }
    except: pass
    return None

def add_bibliography_reference(input_val, importance, notes):
    input_val = input_val.strip()
    data = None
    
    # 判別輸入為 DOI 還是 ISBN
    if input_val.startswith("10.") or "doi.org" in input_val:
        data = fetch_doi_metadata(input_val)
    else:
        import re
        clean_isbn = re.sub(r'[^0-9X]', '', input_val.upper())
        if clean_isbn:
            data = fetch_book_by_isbn(clean_isbn)
            
    if not data:
        return False, "❌ 無法解析該 DOI 或 ISBN，請檢查格式或網路連線。"
        
    try:
        sql = """
        INSERT INTO bibliography_notes 
        (identifier, type, title, author, publisher_journal, issue_volume, publish_date, importance, notes, link, added_date) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(identifier) DO UPDATE SET 
        importance=excluded.importance, notes=excluded.notes;
        """
        db.execute(sql, [
            data['identifier'], data['type'], data['title'], data['author'], 
            data.get('publisher_journal', ''), data.get('issue_volume', ''), 
            data.get('publish_date', ''), importance, notes, data.get('link', ''), 
            datetime.utcnow().isoformat()
        ])
        return True, f"✅ 已成功將《{data['title']}》加入參考書目庫！"
    except Exception as e:
        return False, f"寫入資料庫失敗: {e}"

def fetch_bibliography_references():
    try:
        res = db.execute("SELECT * FROM bibliography_notes ORDER BY added_date DESC")
        return pd.DataFrame([dict(zip(res.columns, row)) for row in res.rows]) if res.rows else pd.DataFrame()
    except:
        return pd.DataFrame()

def update_bibliography_reference(ref_id, importance, notes):
    try:
        db.execute("UPDATE bibliography_notes SET importance = ?, notes = ? WHERE id = ?", [importance, notes, ref_id])
        st.cache_data.clear()
        st.toast("✏️ 參考書目與備註已更新！")
    except Exception as e: st.error(f"更新失敗: {e}")

def delete_bibliography_reference(ref_id):
    try:
        db.execute("DELETE FROM bibliography_notes WHERE id = ?", [ref_id])
        st.cache_data.clear()
        st.toast("🗑️ 參考書目已移除！")
    except Exception as e: st.error(f"刪除失敗: {e}")

# ==========================================
# 書架分類管理模組
# ==========================================
def update_biblio_category(pub_id, new_category):
    try:
        # SQLite 若欄位不存在不會報錯，但我們在爬蟲端其實有預留過 category 欄位
        db.execute("UPDATE academic_pubs SET category = ? WHERE id = ?", [new_category, pub_id])
        st.cache_data.clear()
        st.toast(f"🏷️ 分類已更新為：{new_category}")
    except Exception as e:
        st.error(f"分類更新失敗: {e}")

# ==========================================
# 手動新增與備存寫入防護模組 (MVC 隔離實作)
# ==========================================
def add_manual_book(book_data):
    try:
        sql = """
        INSERT INTO academic_pubs (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image, is_bookmarked, is_manual, category) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, '未分類') 
        ON CONFLICT(identifier) DO UPDATE SET title=excluded.title, image=excluded.image;
        """
        db.execute(sql, [book_data['type'], book_data['title'], book_data['author'], book_data['publisher_journal'], book_data['issue_volume'], book_data['identifier'], book_data['publish_date'], book_data['abstract'], book_data['link'], book_data['image']])
        st.cache_data.clear()
        return True, f"✅ 已將《{book_data['title']}》加入清單！"
    except Exception as e: 
        return False, f"寫入失敗: {e}"

def add_url_backup(url_book_data):
    try:
        sql = """
        INSERT INTO academic_pubs (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image, is_bookmarked, is_manual, category) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, '未分類') 
        ON CONFLICT(identifier) DO UPDATE SET title=excluded.title;
        """
        db.execute(sql, [
            url_book_data['type'], url_book_data['title'], url_book_data['author'], 
            url_book_data['publisher_journal'], url_book_data['issue_volume'], 
            url_book_data['identifier'], url_book_data['publish_date'], 
            url_book_data['abstract'], url_book_data['link'], url_book_data['image']
        ])
        st.cache_data.clear()
        return True, f"📋 備存成功！已將《{url_book_data['title']}》強行歸檔至「網址備存」清單！"
    except Exception as e: 
        return False, f"寫入資料庫失敗: {e}"

# ==========================================
# 🎬 影音館 (Media Vault) 雙 API 穩定引擎
# ==========================================

def insert_media_db(data):
    """將影音資料寫入 Turso 資料庫 (防崩潰 Upsert 版)"""
    try:
        sql = """
        INSERT INTO media_vault (media_type, title, creator, cover_image, release_date, source_url, summary, sort_date, is_bookmarked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(source_url) DO UPDATE SET 
            title=excluded.title, creator=excluded.creator, cover_image=excluded.cover_image, summary=excluded.summary;
        """
        args = [
            data.get('type', 'Unknown'), data.get('title', '未知標題'), data.get('creator', ''),
            data.get('cover', ''), data.get('release_date', '未知時間'), data.get('url', ''),
            data.get('summary', ''), datetime.utcnow().isoformat()
        ]
        db.execute(sql, args)
    except Exception as e:
        print(f"寫入 Media 資料庫失敗: {e}")

def fetch_media_by_broad_type(broad_type):
    """讀取資料庫數據，強制將欄位轉為小寫防止 KeyError"""
    try:
        if broad_type == "Movie":
            res = db.execute("SELECT * FROM media_vault WHERE media_type LIKE '%電影%' OR media_type LIKE '%影集%' ORDER BY sort_date DESC")
        else:
            res = db.execute("SELECT * FROM media_vault WHERE media_type LIKE '%音樂%' OR media_type LIKE '%專輯%' OR media_type LIKE '%單曲%' ORDER BY sort_date DESC")
        
        if not res.rows: return []
        lowercase_columns = [c.lower() for c in res.columns]
        return [dict(zip(lowercase_columns, row)) for row in res.rows]
    except Exception as e:
        print(f"讀取 Media 資料庫失敗: {e}")
        return []

def delete_media_db(media_id):
    try:
        db.execute("DELETE FROM media_vault WHERE id = ?", [media_id])
    except Exception as e:
        print(f"刪除 Media 資料失敗: {e}")

def fetch_media_by_url(user_input, force_type=None):
    """智慧 API 路由器：Apple Music API + TMDB API"""
    user_input = user_input.strip()
    
    # --------------------------------------------------
    # 🎵 模式 A：音樂 (Apple Music API)
    # --------------------------------------------------
    if force_type == "Music" or user_input.isdigit() or "music.apple.com" in user_input:
        apple_id = user_input
        if not user_input.isdigit():
            match = re.search(r'/id(\d+)', user_input) or re.search(r'/(\d+)(?:\?|$)', user_input)
            apple_id = match.group(1) if match else None
            
        if apple_id:
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
            for country in ['tw', 'jp', 'us', 'hk', 'gb']:
                try:
                    api_url = f"https://itunes.apple.com/lookup?id={apple_id}&country={country}"
                    api_res = requests.get(api_url, headers=headers, timeout=10).json()
                    
                    if api_res.get('resultCount', 0) > 0:
                        item = api_res['results'][0]
                        is_track = item.get('wrapperType') == 'track'
                        m_type = "🎵 單曲" if is_track else "🎵 專輯"
                        title = item.get('collectionName') or item.get('trackName') or '未知名稱'
                        creator = item.get('artistName', '未知歌手')
                        img_url = item.get('artworkUrl100', '').replace('100x100bb', '600x600bb')
                        img_b64 = fetch_image_base64(img_url) if img_url else None
                        summary = f"**發行時間:** {item.get('releaseDate', '')[:10]}\n**主要風格:** {item.get('primaryGenreName', '')}"
                        
                        return {"type": m_type, "title": title, "creator": creator, "cover": img_b64, "url": f"https://music.apple.com/album/{apple_id}", "summary": summary}
                except:
                    continue
                    
        return {"type": "🎵 音樂", "title": f"音樂典藏 (ID: {apple_id})", "creator": "未知", "cover": None, "url": f"https://music.apple.com/album/{apple_id}", "summary": "抓取失敗，已安全備存。"}

    # --------------------------------------------------
    # 🎬 模式 B：電影 (TMDB API 突破 IMDb 限制)
    # --------------------------------------------------
    url = user_input
    if not user_input.startswith("http") and user_input.startswith("tt"):
        url = f"https://www.imdb.com/title/{user_input}/"

    if "tt" in url:
        match = re.search(r'(tt\d+)', url)
        if match:
            imdb_id = match.group(1)
            tmdb_api_key = "0539c381c81735a297775971431665a3"
            try:
                tmdb_url = f"https://api.themoviedb.org/3/find/{imdb_id}?api_key={tmdb_api_key}&external_source=imdb_id&language=zh-TW"
                res = requests.get(tmdb_url, timeout=10).json()
                
                if res.get('movie_results'):
                    data = res['movie_results'][0]
                    title = data.get('title') or data.get('original_title') or "未知電影"
                    summary = data.get('overview', '無簡介')
                    poster_path = data.get('poster_path')
                    img_b64 = fetch_image_base64(f"https://image.tmdb.org/t/p/w500{poster_path}") if poster_path else None
                    
                    return {"type": "🎬 電影", "title": title, "creator": "TMDB", "cover": img_b64, "url": f"https://www.imdb.com/title/{imdb_id}/", "summary": summary}
            except Exception as e:
                print(f"TMDB API 查詢失敗: {e}")
                
            return {"type": "🎬 電影", "title": f"IMDb ({imdb_id})", "creator": "未知", "cover": None, "url": f"https://www.imdb.com/title/{imdb_id}/", "summary": "API 抓取失敗，安全備存。"}
            
    return {"type": "🎬 電影", "title": "網路備存電影", "creator": "未知", "cover": None, "url": url, "summary": "非 API 支援網址，已備存。"}
