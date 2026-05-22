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

# ==========================================
# 1. 介面基礎設定 & 全域 CSS 注入
# ==========================================
st.set_page_config(page_title="Monoreader Cloud", page_icon="📚", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.memoof-cover img {
    width: 100%; aspect-ratio: 2 / 3; object-fit: contain; 
    background-color: #1E1E1E; border-radius: 4px;
    box-shadow: 2px 4px 8px rgba(0,0,0,0.3); transition: transform 0.2s ease-in-out;
}
.memoof-cover img:hover { transform: scale(1.03); }
.memoof-meta { margin-top: 10px; text-align: left; }
.memoof-title {
    font-size: 14px; font-weight: bold; line-height: 1.3; color: #E2E8F0; 
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; 
    overflow: hidden; text-overflow: ellipsis; height: 36px;
}
.memoof-author { font-size: 12px; color: #94A3B8; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stButton button { margin-top: 5px; }
</style>
""", unsafe_allow_html=True)

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
    "界面文化": "https://www.jiemian.com/lists/130.html", "Radii": "https://radii.co/"
}
FAST_NEWS_SOURCES = ["WIRED.jp", "CINRA", "VERSE", "界面文化", "Radii", "触乐", "FNMNL"]

def get_source_link(source_name): return SOURCE_URLS.get(source_name.split(" (")[0], "#")

# ==========================================
# 2. 狀態管理與資料庫函數
# ==========================================
if 'mono_page' not in st.session_state: st.session_state.mono_page = 1
if 'biblio_page' not in st.session_state: st.session_state.biblio_page = 1
def reset_mono_page(): st.session_state.mono_page = 1
def reset_biblio_page(): st.session_state.biblio_page = 1
def update_mono_page(): 
    if "mono_page_selector" in st.session_state: st.session_state.mono_page = st.session_state.mono_page_selector
def update_biblio_page(): 
    if "biblio_page_selector" in st.session_state: st.session_state.biblio_page = st.session_state.biblio_page_selector

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
def fetch_academic_pubs(view_mode="探索", pub_type="Book", source_filter="總覽"):
    sql, args = "SELECT * FROM academic_pubs WHERE 1=1", []
    # 🌟 資料庫檢索分流
    if view_mode == "🔖 待讀書架":
        sql += " AND is_bookmarked = 1 AND type != 'Web Link'"
    elif view_mode == "🔗 網址備存":
        sql += " AND type = 'Web Link'"
    else:
        sql += " AND type = ?"; args.append(pub_type)
        if source_filter != "總覽 (依日期遞減)": sql += " AND publisher_journal = ?"; args.append(source_filter)
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

# ==========================================
# 🌟 Biblioapp 手動檢索：語系分流、Base64 與網頁備存引擎
# ==========================================
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
                "image": get_secure_image_base64(img, "google"), "is_bookmarked": 1
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
                "link": f"https://ndlsearch.ndl.go.jp/books/R100000002-I{isbn}", "image": img_url, "is_bookmarked": 1
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
                "abstract": abstract[:600], "link": url, "image": img_url, "is_bookmarked": 1
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
                "image": best_cover if best_cover else info.get("cover", {}).get("large", f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"), "is_bookmarked": 1
            }
    except: pass
    return None

# ==========================================
# 🌟 萬能網址備存解剖器 (Facebook/Twitter 預覽偽裝版)
# ==========================================
def fetch_book_by_url(url):
    if not url.startswith("http"): return None
    
    # 🛡️ 核心破解：偽裝成 Facebook 的官方預覽爬蟲
    # 各大網站(含 Amazon)為了能在社交媒體產生分享預覽卡片，會在防火牆「白名單」無條件放行此 User-Agent
    headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    try:
        # 既然已被白名單放行，我們直接用原生 requests 即可擊穿防護
        res = requests.get(url, headers=headers, timeout=12)
        res.encoding = res.apparent_encoding
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 1. 擷取分享書名 (Twitter Card > Open Graph > 網頁 Title)
            title = ""
            if soup.find('meta', property='og:title'): title = soup.find('meta', property='og:title').get('content')
            elif soup.find('meta', attrs={'name': 'twitter:title'}): title = soup.find('meta', attrs={'name': 'twitter:title'}).get('content')
            elif soup.find('title'): title = soup.find('title').get_text()
            title = title.split('|')[0].split(' - ')[0].replace('Amazon.co.jp:', '').strip() if title else "未命名書籍"
            
            # 2. 擷取分享預覽圖 (Open Graph > Twitter Card)
            img_url = ""
            if soup.find('meta', property='og:image'): img_url = soup.find('meta', property='og:image').get('content')
            elif soup.find('meta', attrs={'name': 'twitter:image'}): img_url = soup.find('meta', attrs={'name': 'twitter:image'}).get('content')
            
            # 如果有圖片，透過 Base64 轉換器安全下載 (避免被再次防盜鏈阻擋)
            if img_url: 
                img_url = get_secure_image_base64(img_url, "social_preview")
            
            # 3. 擷取作者 / 網站名稱
            author = "未知作者"
            author_meta = soup.find('meta', property='article:author') or soup.find('meta', name='twitter:creator') or soup.find('meta', property='og:site_name')
            if author_meta and author_meta.get('content'):
                author = author_meta.get('content').strip()
            
            # 4. 擷取分享摘要
            abstract = "（無摘要）"
            desc_meta = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'twitter:description'}) or soup.find('meta', attrs={'name': 'description'})
            if desc_meta and desc_meta.get('content'):
                abstract = desc_meta.get('content').strip().replace("\n", " ")
            
            # 5. 產生唯一識別碼 (處理 Amazon 重複貼上問題)
            url_hash = f"url_{id(url)}"
            match = re.search(r'dp/([A-Z0-9]{10})|product/([A-Z0-9]{10})|asin/([A-Z0-9]{10})', url, re.I)
            if match: url_hash = f"amazon_{match.group(1) or match.group(2) or match.group(3)}"

            return {
                "type": "Web Link", 
                "title": title, 
                "author": author, 
                "publisher_journal": "網址預覽備存", 
                "issue_volume": "",
                "identifier": url_hash, 
                "publish_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "abstract": abstract[:600], 
                "link": url, 
                "image": img_url, 
                "is_bookmarked": 1
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
# 5. 側邊欄總開關
# ==========================================
with st.sidebar:
    st.title("☁️ Monoreader Cloud")
    app_mode = st.radio("切換平台模組", ["📚 Monoreader", "🎓 Biblioapp"], index=0, label_visibility="collapsed")
    st.divider()

# ==========================================
# 模組一：📚 Monoreader
# ==========================================
if app_mode == "📚 Monoreader":
    st.sidebar.subheader("文章篩選")
    search_input = st.sidebar.text_input("🔍 全文搜尋", placeholder="文章、作者或關鍵字...", on_change=reset_mono_page)
    st.sidebar.markdown("---")
    view_mode = st.sidebar.radio("瀏覽模式", ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊", "🗄️ 分類存檔", "🔖 我的收藏庫", "⏳ 未來典藏"], on_change=reset_mono_page)
    st.sidebar.markdown("---")

    with st.sidebar.expander("📥 手動匯入外部文章", expanded=False):
        external_url = st.text_input("貼上文章網址：", placeholder="https://...")
        if st.button("解析並加入收藏庫", use_container_width=True):
            if external_url.startswith("http"):
                with st.spinner("正在解析網頁內容..."):
                    art_data = fetch_external_article(external_url)
                    if art_data:
                        try:
                            sql = """
                            INSERT INTO articles (Source, Title, Link, Published, Summary, Image, SortDate, is_bookmarked)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                            ON CONFLICT(Link) DO UPDATE SET Title=excluded.Title, Summary=excluded.Summary, Image=excluded.Image;
                            """
                            db.execute(sql, [art_data['Source'], art_data['Title'], art_data['Link'], art_data['Published'], art_data['Summary'], art_data['Image'], art_data['SortDate']])
                            st.cache_data.clear(); st.success("✅ 加入成功！")
                        except Exception as e: st.error(f"寫入資料庫時發生錯誤: {e}")
                    else: st.error("❌ 無法解析該網址。")
            else: st.warning("⚠️ 請輸入包含 http 的完整網址。")

    st.sidebar.markdown("---")
    
    selected_source = "全部來源總覽"
    if view_mode == "🗄️ 分類存檔":
        st.sidebar.subheader("選擇訂閱來源")
        FOLDER_KEYWORDS = ["The Point", "e-flux", "The Funambulist", "421 News", "TripleAmpersand"]
        main_options = []
        for src_key in sorted(SOURCE_URLS.keys()):
            if any(k in src_key for k in FOLDER_KEYWORDS):
                folder_name = f"📁 {src_key.split(' (')[0]}"
                if folder_name not in main_options: main_options.append(folder_name)
            else: main_options.append(src_key)
        main_options.append("🌐 外部手動匯入")
        selected_main = st.sidebar.selectbox("請選擇板塊：", ["全部來源總覽"] + main_options, on_change=reset_mono_page)

        if selected_main.startswith("📁 "):
            base_name = selected_main.replace("📁 ", "")
            res = db.execute("SELECT DISTINCT Source FROM articles WHERE Source LIKE ?", [f"%{base_name}%"])
            raw_sources = [row[0] for row in res.rows]
            def extract_issue_number(source_str):
                match = re.search(r'\d+', source_str)
                return int(match.group()) if match else 0
            all_sub_sources = sorted(raw_sources, key=extract_issue_number, reverse=True)
            if all_sub_sources:
                selected_source = st.sidebar.radio(f"{base_name} 期號/版本：", all_sub_sources, on_change=reset_mono_page)
        else:
            selected_source = selected_main

    if view_mode == "⏳ 未來典藏":
        st.subheader("⏳ 未來典藏 (Future Archive)")
        st.markdown("這裡記錄了已停止更新，但極具歷史考據與思想回溯價值的邊緣文化與次文化資料庫。")
        st.markdown("---")
        st.markdown("### 🇨🇳 異常漫畫研究中心\n🔗 **[前往官網探索](https://search.bilibili.com/all?keyword=異常漫畫研究中心)**<br>", unsafe_allow_html=True)
        st.markdown("### 🌍 AQNB\n🔗 **[前往官網探索](https://www.aqnb.com/)**<br>", unsafe_allow_html=True)
        st.markdown("### 🇯🇵 TOKION\n🔗 **[前往官網探索](https://tokion.jp/)**<br>", unsafe_allow_html=True)
        st.markdown("### 🇨🇳 歪腦 Wainao\n🔗 **[前往官網探索](https://www.wainao.me/)**", unsafe_allow_html=True)

    else:
        df = fetch_data(view_mode, selected_source, search_input)

        if view_mode == "✨ 全部來源總覽":
            st.subheader(f"✨ 全部來源總覽 (過去 24 小時，共 {len(df)} 篇文章)")
            st.caption("打破雜誌界限，即時串流全平台最新擷取到的文化與思想動態。")
        elif view_mode == "✍️ 最新評論":
            st.subheader(f"✍️ 最新思想與文化評論 (過去 24 小時，共 {len(df)} 篇)")
            st.caption("已自動過濾快訊快報，專注收看國內外深度長文、文獻評論與思想探討。")
        elif view_mode == "⚡ 文化快訊":
            st.subheader(f"⚡ 文化與藝術快訊 (過去 24 小時，共 {len(df)} 篇)")
            st.caption("聚合 WIRED.jp、CINRA、VERSE、界面文化、Radii 每日高頻更新的即時消息。")
        elif view_mode == "🔖 我的收藏庫":
            st.subheader(f"🔖 我的收藏庫 (共 {len(df)} 篇)")
        else:
            if selected_source != "全部來源總覽":
                st.subheader(f"🗄️ {selected_source} 存檔 (共 {len(df)} 篇)")
                link = get_source_link(selected_source)
                if link != "#": st.markdown(f"🔗 **[前往該雜誌官網閱讀]({link})**")
            else:
                st.subheader(f"🗄️ 全部來源完整存檔 (顯示最新 500 篇)")

        st.markdown("---")

        if df.empty:
            if search_input: st.info("找不到符合關鍵字的文章。")
            else: st.info("暫無符合條件的新文章。")
        else:
            PER_PAGE = 20
            total_pages = math.ceil(len(df) / PER_PAGE)
            if st.session_state.mono_page > total_pages and total_pages > 0: st.session_state.mono_page = total_pages
            start_idx = (st.session_state.mono_page - 1) * PER_PAGE
            
            for _, row in df.iloc[start_idx:start_idx + PER_PAGE].iterrows():
                with st.container():
                    st.markdown(f"#### [{row['Title']}]({row['Link']})")
                    col_meta, col_btn1, col_btn2 = st.columns([6, 1, 1])
                    with col_meta:
                        raw_pub = str(row['Published'])
                        sort_date = row.get('SortDate')
                        safe_sort_date = str(sort_date).split('T')[0] if pd.notna(sort_date) and sort_date else "未知時間"
                        display_date = f"擷取於 {safe_sort_date}" if any(k in raw_pub for k in ["最新", "Issue", "刊", "None", "nan", "歷史歸檔"]) else raw_pub
                        st.caption(f"🏷️ {row['Source']} | 🕒 {display_date}")
                    
                    is_bk = bool(row.get('is_bookmarked', 0))
                    with col_btn1: st.button("❤️ 已收藏" if is_bk else "🤍 收藏", key=f"bk_{row['Link']}", on_click=toggle_bookmark_db, args=(row['Link'], is_bk))
                    with col_btn2:
                        with st.popover("🗑️"):
                            st.button("確定刪除", key=f"del_{row['Link']}", on_click=delete_article_db, args=(row['Link'],), type="primary", use_container_width=True)
                
                if row['Image'] and str(row['Image']).startswith('http'):
                    img_html = f'<img src="{row["Image"]}" style="width:100%; max-width:800px; border-radius:8px; display:block; margin-bottom:15px; object-fit: cover;" loading="lazy">'
                    st.markdown(img_html, unsafe_allow_html=True)
                st.write(row['Summary'])
                st.markdown("---")

            if total_pages > 1:
                st.write("")
                col_space, col_page, col_space2 = st.columns([1, 2, 1])
                with col_page:
                    st.selectbox("📄 選擇頁數 (跳轉至)：", range(1, total_pages + 1), index=st.session_state.mono_page - 1, key="mono_page_selector", on_change=update_mono_page)

# ==========================================
# 模組二：🎓 Biblioapp
# ==========================================
elif app_mode == "🎓 Biblioapp":
    st.header("🎓 Biblioapp：學術文獻與出版追蹤")
    
    with st.sidebar:
        # 🌟 加入第三分頁：網址備存
        biblio_view_mode = st.radio("功能模式", ["🔍 文獻探索", "🔖 待讀書架", "🔗 網址備存"], on_change=reset_biblio_page)
        st.markdown("---")
        
        with st.expander("📥 手動新增待讀書目 (ISBN)", expanded=False):
            isbn_input = st.text_input("輸入 ISBN：", placeholder="例如: 9780226321486")
            if st.button("檢索並加入書架", use_container_width=True):
                if isbn_input:
                    with st.spinner("正在呼叫多語系智能引擎..."):
                        book_data = fetch_book_by_isbn(isbn_input)
                        if book_data:
                            book_data['publisher_journal'] = "手動加入"
                            try:
                                sql = "INSERT INTO academic_pubs (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image, is_bookmarked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1) ON CONFLICT(identifier) DO UPDATE SET is_bookmarked=1, title=excluded.title, image=excluded.image;"
                                db.execute(sql, [book_data['type'], book_data['title'], book_data['author'], book_data['publisher_journal'], book_data['issue_volume'], book_data['identifier'], book_data['publish_date'], book_data['abstract'], book_data['link'], book_data['image']])
                                st.cache_data.clear(); st.success(f"✅ 已將《{book_data['title']}》加入書架！")
                            except Exception as e: st.error(f"寫入失敗: {e}")
                        else: st.error("❌ 找不到該 ISBN。請嘗試下方的網址備存功能。")
                else: st.warning("⚠️ 請輸入 ISBN。")
        
        # 🌟 新增：網址強制備存輸入區
        with st.expander("📥 網址備存匯入 (當 ISBN 失敗時)", expanded=False):
            backup_url_input = st.text_input("貼上出版社或 Amazon 網址：", placeholder="https://...", key="backup_url_field")
            if st.button("網頁解析並加入備存", use_container_width=True, key="backup_url_btn"):
                if backup_url_input:
                    with st.spinner("正在探測網頁元資料..."):
                        url_book_data = fetch_book_by_url(backup_url_input)
                        if url_book_data:
                            try:
                                sql = """
                                INSERT INTO academic_pubs (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image, is_bookmarked) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1) 
                                ON CONFLICT(identifier) DO UPDATE SET title=excluded.title;
                                """
                                db.execute(sql, [
                                    url_book_data['type'], url_book_data['title'], url_book_data['author'], 
                                    url_book_data['publisher_journal'], url_book_data['issue_volume'], 
                                    url_book_data['identifier'], url_book_data['publish_date'], 
                                    url_book_data['abstract'], url_book_data['link'], url_book_data['image']
                                ])
                                st.cache_data.clear()
                                st.success(f"📋 備存成功！已將《{url_book_data['title']}》強行歸檔至「網址備存」清單！")
                            except Exception as e: 
                                st.error(f"寫入資料庫失敗: {e}")
                        else:
                            st.error("❌ 無法從該網址中萃取出有效的圖書元資料。")
                else:
                    st.warning("⚠️ 請輸入有效的網址。")
        st.markdown("---")

        active_filter = "總覽 (依日期遞減)"
        db_type = "Book"
        if biblio_view_mode == "🔍 文獻探索":
            st.subheader("文獻篩選")
            biblio_type_label = st.radio("文獻類型", ["📚 出版專書", "📄 期刊論文"], label_visibility="collapsed", on_change=reset_biblio_page)
            db_type = "Book" if "專書" in biblio_type_label else "Journal"
            if db_type == "Book":
                active_filter = st.selectbox("選擇出版社：", ["總覽 (依日期遞減)", "MIT Press", "Duke University Press", "青土社", "手動加入"], on_change=reset_biblio_page)
            else:
                active_filter = st.selectbox("選擇期刊：", ["總覽 (依日期遞減)", "青土社 (雜誌)", "PRISM: Theory and Modern Chinese Literature"], on_change=reset_biblio_page)

    df_pubs = fetch_academic_pubs(view_mode=biblio_view_mode, pub_type=db_type, source_filter="青土社" if active_filter == "青土社 (雜誌)" else active_filter)
    
    # ==========================================
    # 畫廊視圖：待讀書架 (包含排序與分頁)
    # ==========================================
    if biblio_view_mode == "🔖 待讀書架":
        if df_pubs.empty:
            st.subheader("🔖 待讀書架 (共 0 本)")
            st.markdown("---")
            st.info("您的待讀書架目前是空的。請在文獻探索中點擊收藏，或在左側透過 ISBN 手動加入。")
        else:
            col_title, col_sort = st.columns([3, 1])
            with col_title:
                st.subheader(f"🔖 待讀書架 (共 {len(df_pubs)} 本)")
            with col_sort:
                bib_sort_mode = st.selectbox(
                    "🔀 書架排序方式：", 
                    ["預設 (依加入順序)", "英文首字母 (A-Z)", "日文五十音", "漢字筆劃/部首"],
                    key="bib_bookshelf_sort"
                )
            st.markdown("---")

            if bib_sort_mode == "英文首字母 (A-Z)":
                df_pubs = df_pubs.sort_values(by='title', key=lambda col: col.str.lower())
            elif bib_sort_mode in ["日文五十音", "漢字筆劃/部首"]:
                df_pubs = df_pubs.sort_values(by='title')

            PER_PAGE_GRID = 15
            total_grid_pages = math.ceil(len(df_pubs) / PER_PAGE_GRID)
            if 'bib_grid_page' not in st.session_state: st.session_state.bib_grid_page = 1
            if st.session_state.bib_grid_page > total_grid_pages: st.session_state.bib_grid_page = max(1, total_grid_pages)
                
            start_grid_idx = (st.session_state.bib_grid_page - 1) * PER_PAGE_GRID
            df_grid_page = df_pubs.iloc[start_grid_idx:start_grid_idx + PER_PAGE_GRID]

            cols = st.columns(5)
            for idx, row in df_grid_page.reset_index(drop=True).iterrows():
                with cols[idx % 5]:
                    img_url = row.get('image')
                    if not img_url or (not str(img_url).startswith("http") and not str(img_url).startswith("data:")):
                        img_url = "https://via.placeholder.com/150x225/2b2b2b/FFFFFF?text=No+Cover"
                        
                    st.markdown(f'''
                    <div class="memoof-book">
                        <a href="{row.get('link', '#')}" target="_blank" class="memoof-cover">
                            <img src="{img_url}" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x225/2b2b2b/FFFFFF?text=No+Cover';">
                        </a>
                        <div class="memoof-meta">
                            <div class="memoof-title" title="{row.get('title', '未命名')}">{row.get('title', '未命名')}</div>
                            <div class="memoof-author" title="{row.get('author', '')}">{row.get('author', '')}</div>
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1: 
                        st.button("💔 移除", key=f"unmark_{row['id']}_{idx}", on_click=toggle_biblio_bookmark_db, args=(row['id'], 1), use_container_width=True)
                    with btn_col2:
                        with st.popover("🗑️ 刪除"):
                            st.write("確定抹除此書？")
                            st.button("✅ 確定", key=f"del_grid_{row['id']}_{idx}", on_click=delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
                    st.write("") 

            if total_grid_pages > 1:
                st.write("")
                col_space, col_page, col_space2 = st.columns([1, 2, 1])
                with col_page:
                    chosen_grid_page = st.selectbox("📄 跳轉書架頁數：", range(1, total_grid_pages + 1), index=st.session_state.bib_grid_page - 1, key="bib_grid_page_selector")
                    if chosen_grid_page != st.session_state.bib_grid_page:
                        st.session_state.bib_grid_page = chosen_grid_page
                        st.rerun()

    # ==========================================
    # 🌟 新增視圖：網址備存專屬列表
    # ==========================================
    elif biblio_view_mode == "🔗 網址備存":
        st.subheader(f"🔗 網址備存清單 (共 {len(df_pubs)} 筆)")
        st.caption("這裡存放了當 ISBN 掃描失敗時，透過網址強制解剖擷取的備用書籍資料。")
        st.markdown("---")
        
        if df_pubs.empty:
            st.info("目前沒有任何網址備存資料。請在左側側邊欄貼上網址匯入。")
        else:
            PER_PAGE = 20
            total_pages = math.ceil(len(df_pubs) / PER_PAGE)
            if st.session_state.biblio_page > total_pages and total_pages > 0: st.session_state.biblio_page = total_pages
            start_idx = (st.session_state.biblio_page - 1) * PER_PAGE
            
            for _, row in df_pubs.iloc[start_idx:start_idx + PER_PAGE].iterrows():
                with st.container():
                    col_info, col_btn = st.columns([8, 1])
                    with col_info:
                        st.markdown(f"### [{row.get('title', '未命名')}]({row.get('link', '#')})")
                        st.caption(f"👤 **Author:** {row.get('author')} | 🌐 **Source:** 網址備存 | 📅 **Date Added:** {row.get('publish_date')}")
                        st.write(row.get('abstract', ''))
                    with col_btn:
                        with st.popover("🗑️ 刪除"):
                            st.write("確定抹除此紀錄？")
                            st.button("✅ 確定", key=f"del_web_{row['id']}", on_click=delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
                st.divider()

            if total_pages > 1:
                col_space, col_page, col_space2 = st.columns([1, 2, 1])
                with col_page:
                    st.selectbox("📄 選擇頁數：", range(1, total_pages + 1), index=st.session_state.biblio_page - 1, key="biblio_page_selector", on_change=update_biblio_page)

    # ==========================================
    # 列表視圖：文獻探索
    # ==========================================
    else:
        st.subheader(f"🏛️ {active_filter} - 目錄 (共 {len(df_pubs)} 筆)")
        st.markdown("---")
        
        if df_pubs.empty:
            st.info("目前資料庫中沒有符合條件的書目。")
        else:
            PER_PAGE = 20
            total_pages = math.ceil(len(df_pubs) / PER_PAGE)
            if st.session_state.biblio_page > total_pages and total_pages > 0: st.session_state.biblio_page = total_pages
            start_idx = (st.session_state.biblio_page - 1) * PER_PAGE
            
            for _, row in df_pubs.iloc[start_idx:start_idx + PER_PAGE].iterrows():
                with st.container():
                    is_bk = bool(row.get('is_bookmarked', 0))
                    if db_type == "Book":
                        col_img, col_info, col_btn = st.columns([2, 6, 1])
                        with col_img:
                            img_url = row.get('image')
                            if pd.notna(img_url) and (str(img_url).startswith("http") or str(img_url).startswith("data:")):
                                img_html = f'''<img src="{img_url}" style="width:100%; max-width:140px; aspect-ratio:2/3; object-fit:contain; background-color:#1E1E1E; border-radius:4px; box-shadow: 0 4px 6px rgba(0,0,0,0.2);" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x225/2b2b2b/FFFFFF?text=No+Cover';">'''
                                st.markdown(img_html, unsafe_allow_html=True)
                            else: st.info("無封面圖影")
                        with col_info:
                            st.markdown(f"### [{row.get('title', '未命名')}]({row.get('link', '#')})")
                            st.caption(f"👤 **Author:** {row.get('author')} | 🏛️ **Publisher:** {row.get('publisher_journal')} | 📅 **Date:** {row.get('publish_date')}")
                            st.write(row.get('abstract', ''))
                        with col_btn:
                            st.button("❤️ 已收" if is_bk else "🤍 收藏", key=f"bk_bib_{row['id']}", on_click=toggle_biblio_bookmark_db, args=(row['id'], is_bk), use_container_width=True)
                            with st.popover("🗑️ 刪除"):
                                st.write("確定抹除此書？")
                                st.button("✅ 確定", key=f"del_list_{row['id']}", on_click=delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
                    else:
                        col_info, col_btn = st.columns([8, 1])
                        with col_info:
                            st.markdown(f"### [{row.get('title', '未命名論文')}]({row.get('link', '#')})")
                            issue_text = f" | 🏷️ **Issue:** {row.get('issue_volume')}" if row.get('issue_volume') else ""
                            st.caption(f"👤 **Author:** {row.get('author')} | 📄 **Journal:** {row.get('publisher_journal')}{issue_text} | 📅 **Date:** {row.get('publish_date')}")
                            st.write(row.get('abstract', ''))
                        with col_btn:
                            st.button("❤️ 已收" if is_bk else "🤍 收藏", key=f"bk_bib_{row['id']}", on_click=toggle_biblio_bookmark_db, args=(row['id'], is_bk), use_container_width=True)
                            with st.popover("🗑️ 刪除"):
                                st.write("確定抹除此論文？")
                                st.button("✅ 確定", key=f"del_list_jour_{row['id']}", on_click=delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
                    st.divider()

            if total_pages > 1:
                col_space, col_page, col_space2 = st.columns([1, 2, 1])
                with col_page:
                    st.selectbox("📄 選擇頁數：", range(1, total_pages + 1), index=st.session_state.biblio_page - 1, key="biblio_page_selector", on_change=update_biblio_page)

st.sidebar.markdown("---")
st.sidebar.caption("Monoreader Cloud v4.0 (Multilingual Router & Web Archive Edition)")
