import streamlit as st
import pandas as pd
import libsql_client
import math
import re
import requests
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ==========================================
# 1. 介面基礎設定 & 全域 CSS 注入
# ==========================================
st.set_page_config(page_title="Monoreader Cloud", page_icon="📚", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.memoof-cover img {
    width: 100%;
    aspect-ratio: 2 / 3; 
    object-fit: contain; 
    background-color: #1E1E1E; 
    border-radius: 4px;
    box-shadow: 2px 4px 8px rgba(0,0,0,0.3);
    transition: transform 0.2s ease-in-out;
}
.memoof-cover img:hover { transform: scale(1.03); }
.memoof-meta { margin-top: 10px; text-align: left; }
.memoof-title {
    font-size: 14px; font-weight: bold; line-height: 1.3;
    color: #E2E8F0; display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis; height: 36px;
}
.memoof-author {
    font-size: 12px; color: #94A3B8; margin-top: 4px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
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

def get_source_link(source_name):
    return SOURCE_URLS.get(source_name.split(" (")[0], "#")

# ==========================================
# 2. 狀態管理
# ==========================================
if 'mono_page' not in st.session_state: st.session_state.mono_page = 1
if 'biblio_page' not in st.session_state: st.session_state.biblio_page = 1

def reset_mono_page(): st.session_state.mono_page = 1
def reset_biblio_page(): st.session_state.biblio_page = 1
def update_mono_page(): 
    if "mono_page_selector" in st.session_state: st.session_state.mono_page = st.session_state.mono_page_selector
def update_biblio_page(): 
    if "biblio_page_selector" in st.session_state: st.session_state.biblio_page = st.session_state.biblio_page_selector

# ==========================================
# 3. 資料庫與所有功能函數 (統一放置於此)
# ==========================================
@st.cache_resource
def init_connection():
    return libsql_client.create_client_sync(url=st.secrets["TURSO_DATABASE_URL"], auth_token=st.secrets["TURSO_AUTH_TOKEN"])
db = init_connection()

@st.cache_data(ttl=600)
def fetch_data(view_mode, source_filter="全部來源總覽", search_query=""):
    sql, args = "SELECT * FROM articles WHERE 1=1", []
    if search_query:
        sql += " AND (Title LIKE ? OR Summary LIKE ?)"
        args.extend([f"%{search_query}%", f"%{search_query}%"])
        if view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽":
            sql += " AND Source = ?"; args.append(source_filter)
        elif view_mode == "🔖 我的收藏庫": sql += " AND is_bookmarked = 1"
    else:
        if view_mode in ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊"]:
            sql += " AND SortDate >= ?"; args.append((datetime.utcnow() - timedelta(hours=24)).isoformat())
        elif view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽":
            sql += " AND Source = ?"; args.append(source_filter)
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
    if view_mode == "🔖 待讀書架":
        sql += " AND is_bookmarked = 1"
    else:
        sql += " AND type = ?"
        args.append(pub_type)
        if source_filter != "總覽 (依日期遞減)":
            sql += " AND publisher_journal = ?"; args.append(source_filter)
    sql += " ORDER BY publish_date DESC LIMIT 500"
    res = db.execute(sql, args)
    if not res.rows: return pd.DataFrame()
    return pd.DataFrame([dict(zip(res.columns, row)) for row in res.rows])

def toggle_bookmark_db(link, current_state):
    try:
        db.execute("UPDATE articles SET is_bookmarked = ? WHERE Link = ?", [0 if current_state else 1, link])
        st.cache_data.clear(); st.toast("書籤狀態已更新！")
    except Exception as e: st.error(f"操作失敗: {e}")

def delete_article_db(link):
    try:
        db.execute("DELETE FROM articles WHERE Link = ?", [link])
        st.cache_data.clear(); st.toast("🗑️ 文章已抹除！")
    except Exception as e: st.error(f"刪除失敗: {e}")

def toggle_biblio_bookmark_db(pub_id, current_state):
    try:
        db.execute("UPDATE academic_pubs SET is_bookmarked = ? WHERE id = ?", [0 if current_state else 1, pub_id])
        st.cache_data.clear(); st.toast("書架狀態已更新！")
    except Exception as e: st.error(f"操作失敗: {e}")

def delete_biblio_db(pub_id):
    try:
        db.execute("DELETE FROM academic_pubs WHERE id = ?", [pub_id])
        st.cache_data.clear(); st.toast("🗑️ 文獻已徹底刪除！")
    except Exception as e: st.error(f"刪除失敗: {e}")

def fetch_book_by_isbn(isbn):
    clean_isbn = re.sub(r'[^0-9X]', '', str(isbn).upper())
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q={clean_isbn}"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if "items" in data and len(data["items"]) > 0:
                info = data["items"][0].get("volumeInfo", {})
                img_links = info.get("imageLinks", {})
                img_url = img_links.get("thumbnail") or img_links.get("smallThumbnail", "")
                img_url = img_url.replace("http://", "https://") if img_url else f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"
                return {
                    "type": "Book", "title": info.get("title", "未命名書籍"), "author": ", ".join(info.get("authors", ["未知作者"])),
                    "publisher_journal": info.get("publisher", "手動加入"), "issue_volume": "",
                    "identifier": clean_isbn, "publish_date": info.get("publishedDate", datetime.utcnow().strftime("%Y-%m-%d")),
                    "abstract": info.get("description", "（無摘要）")[:600],
                    "link": info.get("infoLink", f"https://books.google.com/books?vid=ISBN{clean_isbn}"), "image": img_url, "is_bookmarked": 1
                }
    except: pass
    return None

# ==========================================
# 4. 側邊欄總開關
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
    search_input = st.sidebar.text_input("🔍 全文搜尋", placeholder="關鍵字...", on_change=reset_mono_page)
    st.sidebar.markdown("---")
    view_mode = st.sidebar.radio("瀏覽模式", ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊", "🗄️ 分類存檔", "🔖 我的收藏庫", "⏳ 未來典藏"], on_change=reset_mono_page)
    st.sidebar.markdown("---")
    
    selected_source = "全部來源總覽"
    if view_mode == "🗄️ 分類存檔":
        st.sidebar.subheader("選擇訂閱來源")
        main_options = list(SOURCE_URLS.keys())
        selected_main = st.sidebar.selectbox("請選擇板塊：", ["全部來源總覽"] + main_options, on_change=reset_mono_page)
        selected_source = selected_main

    if view_mode == "⏳ 未來典藏":
        st.subheader("⏳ 未來典藏 (Future Archive)")
        st.info("這裡記錄了極具歷史考據價值的邊緣文化與次文化資料庫。")
    else:
        df = fetch_data(view_mode, selected_source, search_input)
        st.subheader(f"{view_mode.split(' ')[0]} 視圖 (共 {len(df)} 篇)")
        st.markdown("---")

        if df.empty:
            st.info("暫無符合條件的文章。")
        else:
            PER_PAGE = 20
            total_pages = math.ceil(len(df) / PER_PAGE)
            if st.session_state.mono_page > total_pages and total_pages > 0: st.session_state.mono_page = total_pages
            start_idx = (st.session_state.mono_page - 1) * PER_PAGE
            
            for _, row in df.iloc[start_idx:start_idx + PER_PAGE].iterrows():
                with st.container():
                    st.markdown(f"#### [{row['Title']}]({row['Link']})")
                    col_meta, col_btn1, col_btn2 = st.columns([6, 1, 1])
                    with col_meta: st.caption(f"🏷️ {row['Source']} | 🕒 {str(row.get('SortDate', '')).split('T')[0]}")
                    is_bk = bool(row.get('is_bookmarked', 0))
                    with col_btn1: st.button("❤️" if is_bk else "🤍", key=f"bk_{row['Link']}", on_click=toggle_bookmark_db, args=(row['Link'], is_bk))
                    with col_btn2:
                        with st.popover("🗑️"):
                            st.button("確定", key=f"del_{row['Link']}", on_click=delete_article_db, args=(row['Link'],), type="primary")
                
                if row['Image'] and str(row['Image']).startswith('http'):
                    st.markdown(f'<img src="{row["Image"]}" style="width:100%; max-width:800px; border-radius:8px; margin-bottom:15px; object-fit: cover;" loading="lazy">', unsafe_allow_html=True)
                st.write(row['Summary'])
                st.markdown("---")

            if total_pages > 1:
                col_space, col_page, col_space2 = st.columns([1, 2, 1])
                with col_page:
                    st.selectbox("📄 選擇頁數：", range(1, total_pages + 1), index=st.session_state.mono_page - 1, key="mono_page_selector", on_change=update_mono_page)

# ==========================================
# 模組二：🎓 Biblioapp
# ==========================================
elif app_mode == "🎓 Biblioapp":
    st.header("🎓 Biblioapp：學術文獻與出版追蹤")
    
    with st.sidebar:
        biblio_view_mode = st.radio("功能模式", ["🔍 文獻探索", "🔖 待讀書架"], on_change=reset_biblio_page)
        st.markdown("---")
        
        with st.expander("📥 手動新增待讀書目 (ISBN)", expanded=False):
            isbn_input = st.text_input("輸入 ISBN：", placeholder="例如: 9780226321486")
            if st.button("檢索並加入書架", use_container_width=True):
                if isbn_input:
                    with st.spinner("正在呼叫 API..."):
                        book_data = fetch_book_by_isbn(isbn_input)
                        if book_data:
                            book_data['publisher_journal'] = "手動加入"
                            try:
                                sql = "INSERT INTO academic_pubs (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image, is_bookmarked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1) ON CONFLICT(identifier) DO UPDATE SET is_bookmarked=1, title=excluded.title, image=excluded.image;"
                                db.execute(sql, [book_data['type'], book_data['title'], book_data['author'], book_data['publisher_journal'], book_data['issue_volume'], book_data['identifier'], book_data['publish_date'], book_data['abstract'], book_data['link'], book_data['image']])
                                st.cache_data.clear(); st.success(f"✅ 已將《{book_data['title']}》加入書架！")
                            except Exception as e: st.error(f"寫入失敗: {e}")
                        else: st.error("❌ 找不到該 ISBN。")
                else: st.warning("⚠️ 請輸入 ISBN。")
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
    
    if biblio_view_mode == "🔖 待讀書架":
        st.subheader(f"🔖 待讀書架 (共 {len(df_pubs)} 本)")
        st.markdown("---")
        if df_pubs.empty:
            st.info("您的待讀書架目前是空的。")
        else:
            cols = st.columns(5)
            for idx, row in df_pubs.iterrows():
                with cols[idx % 5]:
                    img_url = row.get('image')
                    if not img_url or not str(img_url).startswith("http"):
                        img_url = "https://via.placeholder.com/150x220/2b2b2b/FFFFFF?text=No+Cover"
                        
                    st.markdown(f'''
                    <div class="memoof-book">
                        <a href="{row.get('link', '#')}" target="_blank" class="memoof-cover">
                            <img src="{img_url}" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x220/2b2b2b/FFFFFF?text=No+Cover';">
                        </a>
                        <div class="memoof-meta">
                            <div class="memoof-title" title="{row.get('title', '未命名')}">{row.get('title', '未命名')}</div>
                            <div class="memoof-author" title="{row.get('author', '')}">{row.get('author', '')}</div>
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1: st.button("💔 移除", key=f"unmark_{row['id']}", on_click=toggle_biblio_bookmark_db, args=(row['id'], 1), use_container_width=True)
                    with btn_col2:
                        with st.popover("🗑️ 刪除"):
                            st.write("確定抹除此書？")
                            st.button("✅ 確定", key=f"del_grid_{row['id']}", on_click=delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
                    st.write("") 

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
                            if pd.notna(img_url) and str(img_url).startswith("http"):
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
                                st.write("確定抹除？")
                                st.button("✅ 確定", key=f"del_list_jour_{row['id']}", on_click=delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
                    st.divider()

            if total_pages > 1:
                col_space, col_page, col_space2 = st.columns([1, 2, 1])
                with col_page:
                    st.selectbox("📄 選擇頁數：", range(1, total_pages + 1), index=st.session_state.biblio_page - 1, key="biblio_page_selector", on_change=update_biblio_page)
