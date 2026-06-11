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
import urllib.parse
from PIL import Image
import io

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
    "结绳志": "https://tyingknots.net/", "Pharmakon@Matters": "https://matters.town/@Pharmakon",
    "波士頓書評": "https://bostonreviewofbooks.substack.com/",
    "Caja Negra": "https://cajanegraeditora.com.ar/",
    "Split Infinities": "https://splitinfinities.substack.com/",
    "LARB": "https://lareviewofbooks.org/",
    "FRIEZE": "https://www.frieze.com/"
}
FAST_NEWS_SOURCES = ["WIRED.jp", "CINRA", "VERSE", "界面文化", "Radii", "触乐", "FNMNL"]

def get_source_link(source_name): return SOURCE_URLS.get(source_name.split(" (")[0], "#")

@st.cache_resource
def init_connection(): return libsql_client.create_client_sync(url=st.secrets["TURSO_DATABASE_URL"], auth_token=st.secrets["TURSO_AUTH_TOKEN"])
db = init_connection()

# ==========================================
# 🛠️ 核心共用引擎 (Helpers)
# ==========================================
def get_scraper():
    """全域爬蟲實體生成器，統一管理瀏覽器偽裝與 Timeout"""
    return cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})

def query_to_df(sql, params=None, lower_cols=False):
    """全域 SQL 轉 DataFrame 引擎，取代原本重複的 50 行防呆邏輯"""
    try:
        res = db.execute(sql, params or [])
        if not res.rows: return pd.DataFrame()
        cols = [c.lower() if lower_cols else c for c in res.columns]
        return pd.DataFrame([dict(zip(cols, row)) for row in res.rows])
    except Exception as e:
        print(f"資料庫讀取失敗: {e}")
        return pd.DataFrame()

# ==========================================
# 🛠️ 終極全域 CRUD 引擎 (取代 16 個舊函數)
# ==========================================
def delete_records(table_name, item_ids, id_column="id"):
    """全域統一刪除：支援單筆與多筆，自動清除快取"""
    if not isinstance(item_ids, list): item_ids = [item_ids]
    if not item_ids: return
    try:
        placeholders = ','.join(['?'] * len(item_ids))
        db.execute(f"DELETE FROM {table_name} WHERE {id_column} IN ({placeholders})", item_ids)
        st.cache_data.clear()
        st.toast("🗑️ 資料已刪除！")
    except Exception as e:
        st.error(f"刪除失敗: {e}")

def update_record(table_name, item_id, id_column="id", **kwargs):
    """全域統一更新：自動將 kwargs 轉為 SQL 的 SET 語法"""
    if not kwargs: return False
    try:
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [item_id]
        db.execute(f"UPDATE {table_name} SET {set_clause} WHERE {id_column} = ?", values)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"更新失敗: {e}")
        return False

def toggle_bookmark(table_name, item_ids, to_state, id_column="id"):
    """全域狀態切換：自動將指定的 ID 切換至 to_state 狀態"""
    if not isinstance(item_ids, list): item_ids = [item_ids]
    if not item_ids: return
    try:
        placeholders = ','.join(['?'] * len(item_ids))
        db.execute(f"UPDATE {table_name} SET is_bookmarked = ? WHERE {id_column} IN ({placeholders})", [to_state] + item_ids)
        st.cache_data.clear()
        st.toast("⭐ 狀態已更新！")
    except Exception as e:
        st.error(f"狀態更新失敗: {e}")

# ==========================================
# 📥 資料庫讀取區 
# ==========================================
@st.cache_data(ttl=600)
def fetch_data(view_mode, source_filter="全部來源總覽", search_query=""):
    sql, args = "SELECT * FROM articles WHERE 1=1", []
    if search_query:
        # 🌟 微調點：加入 OR comment LIKE ?，讓全域搜尋也能搜到您寫的筆記！
        sql += " AND (Title LIKE ? OR Summary LIKE ? OR comment LIKE ?)"
        args.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
        if view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽": sql += " AND Source = ?"; args.append(source_filter)
        elif view_mode == "🔖 我的收藏庫": sql += " AND is_bookmarked = 1"
    else:
        if view_mode in ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊"]: sql += " AND SortDate >= ?"; args.append((datetime.utcnow() - timedelta(hours=24)).isoformat())
        elif view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽": sql += " AND Source = ?"; args.append(source_filter)
        elif view_mode == "🔖 我的收藏庫": sql += " AND is_bookmarked = 1"
    sql += " ORDER BY SortDate DESC LIMIT 500"
    
    df = query_to_df(sql, args)
    if not df.empty:
        if view_mode == "✍️ 最新評論": df = df[~df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)]
        elif view_mode == "⚡ 文化快訊": df = df[df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)]
    return df

@st.cache_data(ttl=600)
def fetch_academic_pubs(view_mode="探索", pub_type="Book", source_filter="總覽", search_query=""):
    sql, args = "SELECT * FROM academic_pubs WHERE 1=1", []
    
    # 🌟 核心修復：如果是在「全域搜尋中心」呼叫 (search_query 不為空且 view_mode 為空字串或特定值)
    # 我們就強制略過所有的分類過濾，直接全表搜尋！
    is_global_search = bool(search_query) and view_mode == "🔍 搜尋中心"

    if search_query:
        sql += " AND (title LIKE ? OR author LIKE ? OR abstract LIKE ? OR publisher_journal LIKE ?)"
        like_term = f"%{search_query}%"
        args.extend([like_term, like_term, like_term, like_term])
        
    # 如果是全域搜尋，跳過以下所有的 AND 條件限制
    if not is_global_search:
        if view_mode == "🔖 待讀書架": sql += " AND is_bookmarked = 1 AND type != 'Web Link'"
        elif view_mode == "🔗 網址備存": sql += " AND type = 'Web Link'"
        else:
            sql += " AND type = ?"; args.append(pub_type)
            if source_filter == "手動加入": sql += " AND is_manual = 1"
            elif source_filter != "總覽 (依日期遞減)": sql += " AND publisher_journal = ?"; args.append(source_filter)
            
    sql += " ORDER BY publish_date DESC LIMIT 500"
    return query_to_df(sql, args)

# 🌟 新增 search_query 支援
def fetch_custom_resources(module_name, search_query=""):
    sql = "SELECT * FROM custom_resources WHERE module = ?"
    args = [module_name]
    if search_query:
        sql += " AND (title LIKE ? OR comment LIKE ?)"
        args.extend([f"%{search_query}%", f"%{search_query}%"])
    sql += " ORDER BY added_date DESC"
    return query_to_df(sql, args)

# 🌟 新增 search_query 支援
def fetch_bibliography_references(search_query=""):
    sql = "SELECT * FROM bibliography_notes WHERE 1=1"
    args = []
    if search_query:
        sql += " AND (title LIKE ? OR author LIKE ? OR notes LIKE ?)"
        like_term = f"%{search_query}%"
        args.extend([like_term, like_term, like_term])
    sql += " ORDER BY added_date DESC"
    return query_to_df(sql, args)

# 🌟 新增 search_query 支援
def fetch_media_by_broad_type(broad_type, is_bookmarked=1, search_query=""):
    sql = "SELECT * FROM media_vault WHERE is_bookmarked = ?"
    args = [is_bookmarked]
    
    if broad_type == "Movie":
        sql += " AND (media_type LIKE '%電影%' OR media_type LIKE '%影集%')"
    else:
        sql += " AND (media_type LIKE '%音樂%' OR media_type LIKE '%專輯%' OR media_type LIKE '%單曲%')"
        
    if search_query:
        sql += " AND (title LIKE ? OR creator LIKE ? OR summary LIKE ?)"
        like_term = f"%{search_query}%"
        args.extend([like_term, like_term, like_term])
        
    sql += " ORDER BY sort_date DESC"
    df = query_to_df(sql, args, lower_cols=True)
    return df.to_dict('records') if not df.empty else []

def fetch_crawler_health():
    df = query_to_df("SELECT * FROM crawler_health ORDER BY source_name ASC", lower_cols=True)
    return df.to_dict('records') if not df.empty else []

def fetch_omni_categories():
    res = db.execute("SELECT DISTINCT category FROM omni_vault ORDER BY category")
    return [row[0] for row in res.rows] if res.rows else []

def fetch_omni_items(category=None, search_query=""):
    sql, args = "SELECT * FROM omni_vault WHERE 1=1", []
    if category and category != "全部":
        sql += " AND category = ?"; args.append(category)
    if search_query:
        sql += " AND (title LIKE ? OR comment LIKE ?)"; args.extend([f"%{search_query}%", f"%{search_query}%"])
    sql += " ORDER BY added_date DESC"
    return query_to_df(sql, args)

# ==========================================
# 🌐 網路請求與爬蟲模組 (全面採用 get_scraper)
# ==========================================
def get_secure_image_base64(img_url, source=""):
    """獲取圖片並進行智慧壓縮與降級，大幅減少 Turso 資料庫容量消耗"""
    if not img_url: return ""
    if str(img_url).startswith("data:image"): return img_url
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        if source == "douban": headers["Referer"] = "https://book.douban.com/"
        res = get_scraper().get(img_url, headers=headers, timeout=10)
        
        if res.status_code == 200 and len(res.content) > 500:
            # 🌟 圖片瘦身手術 (Pillow 壓縮機制)
            try:
                # 讀取下載好的二進位圖片
                img = Image.open(io.BytesIO(res.content))
                
                # 轉換為 RGB 模式 (避免 PNG 透明背景轉 JPEG 時變黑或報錯)
                if img.mode in ("RGBA", "P"): 
                    img = img.convert("RGB")
                
                # 強制等比例縮小：最大寬度/高度 300px (對於書籤與卡片來說非常足夠且不影響觀感)
                img.thumbnail((300, 450))
                
                # 將壓縮後的圖片存入記憶體緩衝區 (格式為 JPEG，畫質 75，啟用優化)
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=75, optimize=True)
                compressed_content = buffer.getvalue()
                
                return f"data:image/jpeg;base64,{base64.b64encode(compressed_content).decode('utf-8')}"
                
            except Exception as e:
                # 如果 Pillow 壓縮失敗 (可能不是圖片格式)，退回原始轉換機制
                print(f"圖片壓縮失敗，退回原圖轉碼: {e}")
                return f"data:{res.headers.get('Content-Type', 'image/jpeg')};base64,{base64.b64encode(res.content).decode('utf-8')}"
                
    except: pass
    return img_url

def fetch_external_article(url):
    try:
        res = get_scraper().get(url, timeout=15)
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

def fetch_book_by_url(url):
    if not url.startswith("http"): return None
    try:
        res = get_scraper().get(url, timeout=15)
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
    except Exception as e: print(f"網址備存解析失敗: {e}")
    return None

def fetch_google_fallback(isbn):
    """Google Books API 終極兜底引擎"""
    try:
        # 🛡️ 安全讀取 API Key。請確保您已在 Streamlit Secrets 中設定了 GOOGLE_BOOKS_API_KEY
        api_key = st.secrets.get("GOOGLE_BOOKS_API_KEY", "")
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        if api_key:
            url += f"&key={api_key}"
            
        res = requests.get(url, timeout=10)
        
        if res.status_code == 429:
            print("❌ Google Books API 請求過於頻繁 (429)。")
            return None
        elif res.status_code != 200:
            print(f"❌ Google Books API 伺服器錯誤: {res.status_code}")
            return None
            
        data = res.json()
        if "items" in data and len(data["items"]) > 0:
            info = data["items"][0].get("volumeInfo", {})
            
            # 獲取最高解析度的圖片
            img_links = info.get("imageLinks", {})
            img_url = img_links.get("thumbnail", "") or img_links.get("smallThumbnail", "")
            img_url = img_url.replace("http://", "https://")
            
            # 必須使用我們新版的圖片壓縮函數
            final_image = get_secure_image_base64(img_url, "google") if img_url else ""
            
            return {
                "type": "Book", 
                "title": info.get("title", "未命名書籍"), 
                "author": ", ".join(info.get("authors", [])),
                "publisher_journal": info.get("publisher", "手動加入"), 
                "issue_volume": "", 
                "identifier": isbn, 
                "publish_date": info.get("publishedDate", datetime.utcnow().strftime("%Y-%m-%d")),
                "abstract": info.get("description", "（無摘要）")[:600], 
                "link": info.get("infoLink", ""),
                "image": final_image, 
                "is_bookmarked": 0
            }
    except Exception as e:
        print(f"Google Books API 解析失敗: {e}")
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
    # 🌟 如果 OpenBD 失敗，交由 Google 兜底
    return fetch_google_fallback(isbn)

def fetch_crossref_isbn(isbn):
    try:
        res = requests.get(f"https://api.crossref.org/works?filter=isbn:{isbn}", headers={"User-Agent": "BiblioappCloud/1.0"}, timeout=5).json()
        items = res.get("message", {}).get("items", [])
        if items:
            item = items[0]
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get("author", [])])
            date_parts = item.get("issued", {}).get("date-parts", [[]])[0]
            pub_date = f"{date_parts[0]}-{date_parts[1]:02d}" if len(date_parts) >= 2 else str(date_parts[0]) if date_parts else "未知日期"
            return {
                "type": "Book", "title": item.get("title", ["未命名書籍"])[0], "author": author or "未知",
                "publisher_journal": item.get("publisher", "手動加入"), "issue_volume": "",
                "identifier": isbn, "publish_date": pub_date,
                "abstract": "（由 Crossref 學術庫匯入）", "link": item.get("URL", ""), 
                "image": "", "is_bookmarked": 0
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
        res = get_scraper().get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
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
    # 🌟 如果 Douban 失敗 (例如被擋)，交由 Google 兜底
    return fetch_google_fallback(isbn)

def fetch_book_by_isbn(isbn):
    clean_isbn = re.sub(r'[^0-9X]', '', str(isbn).upper())
    if not clean_isbn: return None
    
    # 1. 根據開頭智能分流 (日文/中文優先)
    if clean_isbn.startswith("9784") or clean_isbn.startswith("9794"): return fetch_openbd(clean_isbn)
    elif clean_isbn.startswith("9787") or clean_isbn.startswith("978957") or clean_isbn.startswith("978986") or clean_isbn.startswith("978626"): return fetch_douban(clean_isbn)
    
    # 2. 獲取 Syndetics 高清書影備用
    best_cover = ""
    try:
        syn_res = requests.get(f"https://syndetics.com/index.aspx?isbn={clean_isbn}/lc.jpg&client=test", timeout=5)
        if syn_res.status_code == 200 and len(syn_res.content) > 100: best_cover = f"https://syndetics.com/index.aspx?isbn={clean_isbn}/lc.jpg&client=test"
    except: pass

    # 3. 🌟 主力英文兜底：直接呼叫 Google Books
    res = fetch_google_fallback(clean_isbn)
    if res:
        if best_cover and not res.get("image"): res["image"] = best_cover
        return res
        
    # 4. 如果連 Google 都沒有，才退到 Crossref (通常只有標題沒有封面)
    res_crossref = fetch_crossref_isbn(clean_isbn)
    if res_crossref:
        if best_cover: res_crossref["image"] = best_cover
        return res_crossref
        
    # 5. 最後的最後：Open Library
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

def fetch_apple_music_data(url_or_id):
    apple_id = url_or_id.strip()
    if not apple_id.isdigit():
        match = re.search(r'/id(\d+)', url_or_id) or re.search(r'/(\d+)(?:\?|$)', url_or_id)
        apple_id = match.group(1) if match else None
    if not apple_id: return None

    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    for country in ['tw', 'jp', 'us', 'hk']:
        try:
            res = requests.get(f"https://itunes.apple.com/lookup?id={apple_id}&country={country}", headers=headers, timeout=10).json()
            if res.get('resultCount', 0) > 0:
                item = res['results'][0]
                img_url = item.get('artworkUrl100', '').replace('100x100bb', '600x600bb')
                return {
                    "media_type": "🎵 音樂", "title": item.get('collectionName') or item.get('trackName', '未知專輯'),
                    "creator": item.get('artistName', '未知音樂家'), "cover_image": get_secure_image_base64(img_url) if img_url else None,
                    "source_url": item.get('collectionViewUrl', url_or_id), "summary": f"Apple Music ({country.upper()}區) 典藏"
                }
        except: continue
    return None

def fetch_movie_data(url):
    match = re.search(r'(tt\d+)', url)
    if not match: return None
    imdb_id = match.group(1)
    target_url = f"https://www.imdb.com/title/{imdb_id}/"

    tmdb_key = st.secrets.get("TMDB_API_KEY") if hasattr(st, "secrets") else None
    if tmdb_key:
        try:
            tmdb_url = f"https://api.themoviedb.org/3/find/{imdb_id}?api_key={tmdb_key}&external_source=imdb_id&language=zh-TW"
            res = requests.get(tmdb_url, timeout=10).json()
            if res.get('movie_results'):
                data = res['movie_results'][0]
                tmdb_id = data.get('id')
                creator_name = "TMDB"
                if tmdb_id:
                    try:
                        credits_res = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits?api_key={tmdb_key}&language=zh-TW", timeout=5).json()
                        directors = [crew['name'] for crew in credits_res.get('crew', []) if crew.get('job') == 'Director']
                        if directors: creator_name = ", ".join(directors)
                    except: pass
                img_url = f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None
                return {
                    "media_type": "🎬 電影", "title": data.get('title') or data.get('original_title', '未知電影'),
                    "creator": creator_name, "cover_image": get_secure_image_base64(img_url, "tmdb") if img_url else None,
                    "source_url": target_url, "summary": data.get('overview', '無簡介')
                }
        except: pass

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        soup = BeautifulSoup(requests.get(target_url, headers=headers, timeout=15).text, 'html.parser')
        ld_json = soup.find('script', type='application/ld+json')
        title, img_url, summary = f"IMDb ({imdb_id})", None, "IMDb 備存"
        if ld_json:
            import json
            try:
                data = json.loads(ld_json.string)
                if isinstance(data, list): data = data[0]
                title = data.get('name', title)
                img_url = data.get('image')
                summary = data.get('description', summary)
            except: pass
        if not img_url and soup.find('meta', property='og:image'): img_url = soup.find('meta', property='og:image')['content']
        return {
            "media_type": "🎬 電影", "title": title, "creator": "IMDb",
            "cover_image": get_secure_image_base64(img_url, "imdb") if img_url else None,
            "source_url": target_url, "summary": summary
        }
    except Exception as e: print(f"IMDb 爬蟲失敗: {e}")
    return None

def fetch_doi_metadata(doi):
    clean_doi = doi.replace("https://doi.org/", "").strip()
    try:
        res = requests.get(f"https://doi.org/{clean_doi}", headers={"Accept": "application/vnd.citationstyles.csl+json", "User-Agent": "BiblioappCloud/1.0"}, timeout=10, allow_redirects=True)
        if res.status_code == 200:
            item = res.json()
            author = ", ".join([f"{a.get('given', '')} {a.get('family', '')}".strip() for a in item.get("author", [])])
            container = item.get("container-title", "")
            vol, iss = item.get("volume", ""), item.get("issue", "")
            issue_vol = f"Vol. {vol}, Issue {iss}" if vol and iss else (f"Issue {iss}" if iss else "")
            date_parts = item.get("issued", {}).get("date-parts", [[]])[0]
            pub_date = f"{date_parts[0]}-{date_parts[1]:02d}" if len(date_parts) >= 2 else str(date_parts[0]) if date_parts else "未知日期"
            
            return {
                "type": "Journal" if container else "Book", "title": item.get("title", "未命名文獻"), 
                "author": author, "publisher_journal": container if container else item.get("publisher", ""),
                "issue_volume": issue_vol, "identifier": clean_doi, "publish_date": pub_date,
                "link": item.get("URL", f"https://doi.org/{clean_doi}")
            }
    except Exception as e: print(f"DOI 解析失敗: {e}")
    return None

def fetch_from_openalex_by_title(title):
    clean_title = urllib.parse.quote(title.strip())
    try:
        res = requests.get(f"https://api.openalex.org/works?search={clean_title}&per-page=1", headers={"User-Agent": "BiblioappCloud/1.0"}, timeout=10).json()
        if res.get("meta", {}).get("count", 0) > 0:
            item = res["results"][0]
            author = ", ".join([a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])])
            source = item.get("primary_location", {}) or {}
            doi_link = item.get("doi", "")
            return {
                "type": "Journal" if "article" in item.get("type", "") else "Book",
                "title": item.get("title", "未命名"), "author": author or "未知",
                "publisher_journal": (source.get("source", {}) or {}).get("display_name") or source.get("publisher", "未知出版方"), 
                "issue_volume": "", "identifier": doi_link.replace("https://doi.org/", "") if doi_link else item.get("id", ""), 
                "publish_date": item.get("publication_date", "未知日期"),
                "abstract": "（由 OpenAlex 標題盲搜匯入）", "link": doi_link or item.get("id", ""), "image": "", "is_bookmarked": 0
            }
    except Exception as e: print(f"OpenAlex 標題搜尋失敗: {e}")
    return None

# ==========================================
# 📥 寫入與新增模組區 (保持原樣，直接對接 DB)
# ==========================================
def init_bibliography_table():
    try:
        db.execute("CREATE TABLE IF NOT EXISTS bibliography_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, identifier TEXT UNIQUE, type TEXT, title TEXT, author TEXT, publisher_journal TEXT, issue_volume TEXT, publish_date TEXT, importance TEXT, notes TEXT, link TEXT, added_date TEXT)")
    except Exception: pass
init_bibliography_table()

def init_health_table():
    try:
        db.execute("CREATE TABLE IF NOT EXISTS crawler_health (source_name TEXT PRIMARY KEY, status TEXT, last_check TEXT, error_msg TEXT)")
    except Exception: pass
init_health_table()

def add_custom_resource(module_name, url):
    if not url.startswith("http"): return False, "⚠️ 請輸入完整的網址 (包含 http)"
    title = "未命名網站"
    try:
        res = get_scraper().get(url, timeout=15)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            if soup.find('meta', property='og:title'): title = soup.find('meta', property='og:title').get('content')
            elif soup.find('meta', attrs={'name': 'twitter:title'}): title = soup.find('meta', attrs={'name': 'twitter:title'}).get('content')
            elif soup.find('title'): title = soup.find('title').get_text()
            if title and title != "未命名網站": title = title.split('|')[0].split(' - ')[0].strip()
            else: title = "未命名網站"
    except Exception: pass
    try:
        db.execute("INSERT INTO custom_resources (module, title, url, added_date) VALUES (?, ?, ?, ?) ON CONFLICT(url) DO UPDATE SET title=excluded.title", [module_name, title, url, datetime.utcnow().isoformat()])
        st.cache_data.clear()
        return True, f"✅ 已成功加入清單！"
    except Exception as e: return False, f"❌ 資料庫寫入錯誤: {e}"

def add_bibliography_reference(input_val, importance, notes):
    input_val = input_val.strip()
    data = fetch_doi_metadata(input_val) if input_val.startswith("10.") or "doi.org" in input_val else fetch_book_by_isbn(re.sub(r'[^0-9X]', '', input_val.upper()))
    if not data: return False, "❌ 無法解析該 DOI 或 ISBN"
    try:
        sql = "INSERT INTO bibliography_notes (identifier, type, title, author, publisher_journal, issue_volume, publish_date, importance, notes, link, added_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(identifier) DO UPDATE SET importance=excluded.importance, notes=excluded.notes;"
        db.execute(sql, [data['identifier'], data['type'], data['title'], data['author'], data.get('publisher_journal', ''), data.get('issue_volume', ''), data.get('publish_date', ''), importance, notes, data.get('link', ''), datetime.utcnow().isoformat()])
        st.cache_data.clear()
        return True, f"✅ 已成功將《{data['title']}》加入參考書目庫！"
    except Exception as e: return False, f"寫入失敗: {e}"

def add_manual_book(book_data):
    try:
        sql = "INSERT INTO academic_pubs (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image, is_bookmarked, is_manual, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, '未分類') ON CONFLICT(identifier) DO UPDATE SET title=excluded.title, image=excluded.image;"
        db.execute(sql, [book_data['type'], book_data['title'], book_data['author'], book_data['publisher_journal'], book_data['issue_volume'], book_data['identifier'], book_data['publish_date'], book_data['abstract'], book_data['link'], book_data['image']])
        st.cache_data.clear()
        return True, f"✅ 已將《{book_data['title']}》加入清單！"
    except Exception as e: return False, f"寫入失敗: {e}"

def add_url_backup(url_book_data):
    try:
        sql = "INSERT INTO academic_pubs (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image, is_bookmarked, is_manual, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, '未分類') ON CONFLICT(identifier) DO UPDATE SET title=excluded.title;"
        db.execute(sql, [url_book_data['type'], url_book_data['title'], url_book_data['author'], url_book_data['publisher_journal'], url_book_data['issue_volume'], url_book_data['identifier'], url_book_data['publish_date'], url_book_data['abstract'], url_book_data['link'], url_book_data['image']])
        st.cache_data.clear()
        return True, f"📋 備存成功！已將《{url_book_data['title']}》強行歸檔至「網址備存」清單！"
    except Exception as e: return False, f"寫入失敗: {e}"

def insert_media_db(data):
    try:
        sql = "INSERT INTO media_vault (media_type, title, creator, cover_image, release_date, source_url, summary, sort_date, is_bookmarked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(source_url) DO UPDATE SET title=excluded.title, creator=excluded.creator, cover_image=excluded.cover_image, summary=excluded.summary, is_bookmarked=excluded.is_bookmarked;"
        args = [data.get('media_type', 'Unknown'), data.get('title', '未知標題'), data.get('creator', ''), data.get('cover_image', ''), '未知時間', data.get('source_url', ''), data.get('summary', ''), datetime.utcnow().isoformat(), data.get('is_bookmarked', 1)]
        db.execute(sql, args)
    except Exception as e: print(f"寫入 Media 失敗: {e}")

def add_book_by_title_blind_search(title):
    try:
        book_data = fetch_from_openalex_by_title(title)
        if not book_data: return False, "❌ 無法在 OpenAlex 找到相符文獻。"
        sql = "INSERT INTO academic_pubs (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image, is_bookmarked, is_manual, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, '未分類') ON CONFLICT(identifier) DO UPDATE SET title=excluded.title;"
        db.execute(sql, [book_data['type'], book_data['title'], book_data['author'], book_data['publisher_journal'], book_data['issue_volume'], book_data['identifier'], book_data['publish_date'], book_data['abstract'], book_data['link'], book_data['image']])
        st.cache_data.clear()
        return True, f"✅ 盲搜成功！已將《{book_data['title']}》加入清單！"
    except Exception as e: return False, f"寫入失敗: {e}"

def add_manual_bibliography_reference(identifier, title, author, importance, notes, pub_year, pub_type):
    identifier = str(identifier).strip()
    if not identifier: return False, "❌ 必須提供真實的 DOI 或 ISBN 作為唯一識別碼。"
    safe_date = f"{pub_year}-01-01" if pub_year and str(pub_year).isdigit() else "未知年份"
    db_type = "Book" if pub_type == "專書 (Book)" else "Journal"
    try:
        sql = "INSERT INTO bibliography_notes (identifier, type, title, author, publisher_journal, issue_volume, publish_date, importance, notes, link, added_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(identifier) DO UPDATE SET title=excluded.title, author=excluded.author, importance=excluded.importance, notes=excluded.notes, type=excluded.type, publish_date=excluded.publish_date;"
        db.execute(sql, [identifier, db_type, title.strip(), author.strip(), "手動加入", "", safe_date, importance, notes, "", datetime.utcnow().isoformat()])
        return True, f"✅ 已成功手動加入參考庫！"
    except Exception as e: return False, f"寫入失敗: {e}"

def add_manual_custom_resource(module, title, url, comment):
    if not title: return False, "❌ 名稱/主題為必填欄位。"
    safe_url = url.strip() if url and url.strip() != "" else f"local_record_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    try:
        db.execute("INSERT INTO custom_resources (module, title, url, comment, added_date) VALUES (?, ?, ?, ?, ?)", [module, title, safe_url, comment, datetime.utcnow().isoformat()])
        st.cache_data.clear()
        return True, f"✅ 已成功記錄：《{title}》"
    except Exception as e: return False, f"寫入失敗: {e}"

def add_omni_item(category, title, url, comment, image_url=""):
    if not title or not category: return False, "分類與名稱為必填欄位。"
    try:
        db.execute("INSERT INTO omni_vault (category, title, url, comment, image_url) VALUES (?, ?, ?, ?, ?)", [category, title, url, comment, image_url])
        return True, "✅ 收藏成功！"
    except Exception as e: return False, f"寫入失敗: {e}"
