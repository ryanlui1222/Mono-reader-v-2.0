import streamlit as st
import pandas as pd
import libsql_client
import math
import re
import requests
import cloudscraper  # 用於突破外部網站的手動匯入防火牆
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ==========================================
# 1. 介面基礎設定 (唯一全域宣告)
# ==========================================
st.set_page_config(
    page_title="Monoreader Cloud", 
    page_icon="📚", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

SOURCE_URLS = {
    # --- 📚 深度長文 / 評論 ---
    "Aeon 思想誌": "https://aeon.co/",
    "New Yorker, Books and Culture": "https://www.newyorker.com/culture",
    "421 News (EN)": "https://www.421.news/en",
    "421 News (ZH)": "https://www.421.news/zh",
    "聯經思想空間": "https://www.linking.vision/",
    "上海書評": "https://www.thepaper.cn/list_25444",
    "藝術界": "https://www.leapleapleap.com/",
    "MIT Press Reader": "https://thereader.mitpress.mit.edu/",
    "webゲンロン": "https://webgenron.com/",
    "e-flux Journal": "https://www.e-flux.com/journal/",
    "Eurozine": "https://www.eurozine.com/essays/",
    "美術手帖": "https://bijutsutecho.com/magazine/series",
    "澎湃思想市場": "https://www.thepaper.cn/list_25483",
    "Verso Blog": "https://www.versobooks.com/blogs/news",
    "The Point": "https://thepointmag.com/magazine/",
    "The Funambulist": "https://thefunambulist.net/",
    "BIE別的": "https://www.biede.com/",
    "Sabukaru": "https://sabukaru.online/articles", 
    "TripleAmpersand": "https://tripleampersand.org/", 
    
    # --- ⚡ 文化快訊 / 消息 ---
    "WIRED.jp": "https://wired.jp/",
    "CINRA": "https://www.cinra.net/",
    "VERSE": "https://www.verse.com.tw/",
    "界面文化": "https://www.jiemian.com/lists/130.html",
    "Radii": "https://radii.co/"
}

# 🌟 更新排他過濾名單（加入 触乐 與 FNMNL）
FAST_NEWS_SOURCES = ["WIRED.jp", "CINRA", "VERSE", "界面文化", "Radii", "触乐", "FNMNL"]

def get_source_link(source_name):
    base_name = source_name.split(" (")[0]
    return SOURCE_URLS.get(base_name, "#")

# ==========================================
# 2. 狀態管理 (Session State)
# ==========================================
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1

def reset_page():
    st.session_state.current_page = 1

def update_page():
    st.session_state.current_page = st.session_state.page_selector

# ==========================================
# 3. 雲端資料庫連線與資料操作 (Turso SQLite)
# ==========================================
@st.cache_resource
def init_connection():
    return libsql_client.create_client_sync(
        url=st.secrets["TURSO_DATABASE_URL"],
        auth_token=st.secrets["TURSO_AUTH_TOKEN"]
    )

db = init_connection()

@st.cache_data(ttl=600)
def fetch_data(view_mode, source_filter="全部來源總覽", search_query=""):
    sql = "SELECT * FROM articles WHERE 1=1"
    args = []
    
    # 🔍 全文搜尋模式
    if search_query:
        sql += " AND (Title LIKE ? OR Summary LIKE ?)"
        args.extend([f"%{search_query}%", f"%{search_query}%"])
        if view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽":
            sql += " AND Source = ?"
            args.append(source_filter)
        elif view_mode == "🔖 我的收藏庫":
            sql += " AND is_bookmarked = 1"
            
    # 🕒 時間與過濾模式
    else:
        if view_mode in ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊"]:
            time_threshold = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            sql += " AND SortDate >= ?"
            args.append(time_threshold)
        elif view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽":
            sql += " AND Source = ?"
            args.append(source_filter)
        elif view_mode == "🔖 我的收藏庫":
            sql += " AND is_bookmarked = 1"
        
    sql += " ORDER BY SortDate DESC LIMIT 500"
    
    res = db.execute(sql, args)
    
    if not res.rows: 
        return pd.DataFrame()
        
    df = pd.DataFrame([dict(zip(res.columns, row)) for row in res.rows])
    
    # 分流過濾邏輯
    if view_mode == "✍️ 最新評論":
        mask = df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)
        df = df[~mask]
    elif view_mode == "⚡ 文化快訊":
        mask = df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)
        df = df[mask]
        
    return df

def toggle_bookmark_db(link, current_state):
    try:
        new_state = 0 if current_state else 1
        db.execute("UPDATE articles SET is_bookmarked = ? WHERE Link = ?", [new_state, link])
        st.cache_data.clear()
        st.toast("書籤狀態已更新！")
    except Exception as e:
        st.error(f"操作失敗: {e}")

# 🌟 新增：手動刪除文章功能
def delete_article_db(link):
    try:
        db.execute("DELETE FROM articles WHERE Link = ?", [link])
        st.cache_data.clear()
        st.toast("🗑️ 文章已成功從雲端抹除！")
    except Exception as e:
        st.error(f"刪除失敗: {e}")

# ==========================================
# 🌟 萬能外部文章解析器 (Universal Scraper)
# ==========================================
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
        
        return {
            "Source": "🌐 外部手動匯入",
            "Title": title.strip(),
            "Link": url,
            "Published": "手動收藏",
            "Summary": final_summary,
            "Image": img_url,
            "SortDate": datetime.utcnow().isoformat(),
            "is_bookmarked": 1
        }
    except Exception as e:
        print(f"解析外部文章失敗: {e}")
        return None

# ==========================================
# 4. 介面渲染：側邊欄 (Sidebar)
# ==========================================
st.sidebar.title("📚 Monoreader")

search_input = st.sidebar.text_input("🔍 全文搜尋", placeholder="文章、作者或關鍵字...", on_change=reset_page)
st.sidebar.markdown("---")

view_mode = st.sidebar.radio(
    "瀏覽模式", 
    ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊", "🗄️ 分類存檔", "🔖 我的收藏庫", "⏳ 未來典藏"], 
    on_change=reset_page
)
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
                        st.cache_data.clear()
                        st.success("✅ 已成功解析並加入我的收藏庫！")
                    except Exception as e:
                        st.error(f"寫入資料庫時發生錯誤: {e}")
                else:
                    st.error("❌ 無法解析該網址，可能是對方網站阻擋了機器人訪問。")
        else:
            st.warning("⚠️ 請輸入包含 http 的完整網址。")

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
        else:
            main_options.append(src_key)
            
    main_options.append("🌐 外部手動匯入")
            
    selected_main = st.sidebar.selectbox("請選擇板塊：", ["全部來源總覽"] + main_options, on_change=reset_page)

    if selected_main.startswith("📁 "):
        base_name = selected_main.replace("📁 ", "")
        res = db.execute("SELECT DISTINCT Source FROM articles WHERE Source LIKE ?", [f"%{base_name}%"])
        raw_sources = [row[0] for row in res.rows]
        
        def extract_issue_number(source_str):
            match = re.search(r'\d+', source_str)
            return int(match.group()) if match else 0
            
        all_sub_sources = sorted(raw_sources, key=extract_issue_number, reverse=True)
        if all_sub_sources:
            selected_source = st.sidebar.radio(f"{base_name} 期號/版本：", all_sub_sources, on_change=reset_page)
    else:
        selected_source = selected_main

# ==========================================
# 5. 介面渲染：主畫面 (Main View)
# ==========================================
if view_mode == "⏳ 未來典藏":
    st.subheader("⏳ 未來典藏 (Future Archive)")
    st.markdown("這裡記錄了已停止更新，但極具歷史考據與思想回溯價值的邊緣文化與次文化資料庫。")
    st.markdown("---")
    
    st.markdown("### 🇨🇳 異常漫畫研究中心")
    st.caption("聚焦於另類漫畫 (Alternative Manga)、地下藝術與 Garo (ガロ) 系系譜的中文硬核考據誌。")
    st.markdown("🔗 **[前往官網探索](https://search.bilibili.com/all?keyword=異常漫畫研究中心)**")
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("### 🌍 AQNB")
    st.caption("專注於後網路藝術 (Post-Internet Art)、前衛數位美學、CGI 視覺與實驗電子音樂演變的海外先鋒平台。")
    st.markdown("🔗 **[前往官網探索](https://www.aqnb.com/)**")
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("### 🇯🇵 TOKION")
    st.caption("停更於 2024 年。日本前衛流行、藝術、電影與當代潮流次文化的重要指標。")
    st.markdown("🔗 **[前往官網探索](https://tokion.jp/)**")
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("### 🇨🇳 歪腦 Wainao")
    st.caption("停更於 2025 年。專注於新世代華語青年、邊緣視角與深度的社會紀實觀察。")
    st.markdown("🔗 **[前往官網探索](https://www.wainao.me/)**")

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
        if st.session_state.current_page > total_pages and total_pages > 0:
            st.session_state.current_page = total_pages
            
        start_idx = (st.session_state.current_page - 1) * PER_PAGE
        end_idx = start_idx + PER_PAGE
        
        for _, row in df.iloc[start_idx:end_idx].iterrows():
            with st.container():
                st.markdown(f"#### [{row['Title']}]({row['Link']})")
# 將版面切分為 3 個欄位，讓按鈕獨立且緊湊
                col_meta, col_btn1, col_btn2 = st.columns([6, 1, 1])
                
                with col_meta:
                    raw_pub = str(row['Published'])
                    sort_date = row.get('SortDate')
                    
                    safe_sort_date = str(sort_date).split('T')[0] if pd.notna(sort_date) and sort_date else "未知時間"
                    display_date = f"擷取於 {safe_sort_date}" if any(k in raw_pub for k in ["最新", "Issue", "刊", "None", "nan", "歷史歸檔"]) else raw_pub
                    st.caption(f"🏷️ {row['Source']} | 🕒 {display_date}")
                
                # 🌟 整合：縮小按鈕並加入「刪除確認」的防呆機制
                is_bk = bool(row.get('is_bookmarked', 0))
                
                with col_btn1:
                    # 移除了 use_container_width=True，按鈕會自然縮小
                    st.button("❤️ 已收藏" if is_bk else "🤍 收藏", key=f"bk_{row['Link']}", 
                              on_click=toggle_bookmark_db, args=(row['Link'], is_bk))
                              
                with col_btn2:
                    # 使用 st.popover 製作優雅的確認彈出視窗
                    with st.popover("🗑️ 刪除"):
                        st.markdown("⚠️ **確認刪除嗎？**")
                        # 確認按鈕設定為 type="primary" (紅色醒目提示)
                        st.button("✅ 確定", key=f"del_{row['Link']}", 
                                  on_click=delete_article_db, args=(row['Link'],), 
                                  type="primary", use_container_width=True)
                if row['Image'] and str(row['Image']).startswith('http'):
                    img_html = f'<img src="{row["Image"]}" style="width:100%; max-width:800px; border-radius:8px; display:block; margin-bottom:15px; object-fit: cover;" loading="lazy">'
                    st.markdown(img_html, unsafe_allow_html=True)
                    
                st.write(row['Summary'])
                st.markdown("---")

        if total_pages > 1:
            st.write("")
            col_space, col_page, col_space2 = st.columns([1, 2, 1])
            with col_page:
                st.selectbox(
                    "📄 選擇頁數 (跳轉至)：", 
                    range(1, total_pages + 1), 
                    index=st.session_state.current_page - 1, 
                    key="page_selector", 
                    on_change=update_page
                )
                st.caption(f"目前顯示第 {st.session_state.current_page} 頁，共 {total_pages} 頁")

st.sidebar.markdown("---")
st.sidebar.caption("Monoreader Cloud v3.2 (Powered by Turso & Cloudscraper)")
