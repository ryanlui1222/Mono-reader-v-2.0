import streamlit as st
import pandas as pd
from supabase import create_client, Client
import math
import re
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
    # --- ⚡ 文化快訊 / 消息 ---
    "WIRED.jp": "https://wired.jp/",
    "CINRA": "https://www.cinra.net/",
    "VERSE": "https://www.verse.com.tw/"
}

# 🌟 排他過濾名單（僅包含三家高頻率快訊媒體）
FAST_NEWS_SOURCES = ["WIRED.jp", "CINRA", "VERSE"]

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
# 3. 雲端資料庫連線與資料操作
# ==========================================
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

@st.cache_data(ttl=600)
def fetch_data(view_mode, source_filter="全部來源總覽", search_query=""):
    query = supabase.table('articles').select("*")
    
    if view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽":
        query = query.eq("Source", source_filter)
    elif view_mode == "🔖 我的收藏庫":
        query = query.eq("is_bookmarked", True)
        
    if search_query:
        query = query.or_(f'Title.ilike.%{search_query}%,Summary.ilike.%{search_query}%')
        
    res = query.order("SortDate", desc=True).limit(500).execute()
    df = pd.DataFrame(res.data)
    
    if df.empty:
        return df
        
    # 智慧流量分流邏輯
    if view_mode == "✍️ 最新評論":
        mask = df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)
        df = df[~mask]
    elif view_mode == "⚡ 文化快訊":
        mask = df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)
        df = df[mask]
        
    return df

def toggle_bookmark_db(link, current_state):
    """切換收藏狀態 (已補回)"""
    try:
        supabase.table('articles').update({"is_bookmarked": not current_state}).eq("Link", link).execute()
        st.cache_data.clear() # 強制刷新快取
        st.toast("書籤狀態已更新！")
    except Exception as e:
        st.error(f"操作失敗: {e}")

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

selected_source = "全部來源總覽"
if view_mode == "🗄️ 分類存檔":
    st.sidebar.subheader("選擇訂閱來源")
    
    FOLDER_KEYWORDS = ["The Point", "e-flux", "The Funambulist", "421 News"]
    main_options = []
    for src_key in sorted(SOURCE_URLS.keys()):
        if any(k in src_key for k in FOLDER_KEYWORDS):
            folder_name = f"📁 {src_key.split(' (')[0]}"
            if folder_name not in main_options: main_options.append(folder_name)
        else:
            main_options.append(src_key)
            
    selected_main = st.sidebar.selectbox("請選擇板塊：", ["全部來源總覽"] + main_options, on_change=reset_page)

    if selected_main.startswith("📁 "):
        base_name = selected_main.replace("📁 ", "")
        res = supabase.table('articles').select('Source').ilike('Source', f'%{base_name}%').execute()
        raw_sources = list(set([r['Source'] for r in res.data]))
        
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
    st.markdown("這裡記錄了已停止更新，但值得未來編寫回溯腳本導入的歷史文化資料庫。")
    st.markdown("---")
    st.markdown("### 🇯🇵 TOKION")
    st.caption("停更於 2024 年。日本前衛流行、藝術與當代潮流次文化的重要指標。")
    st.markdown("🔗 **[前往官網探索](https://tokion.jp/)**")
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🇨🇳 歪腦 Wainao")
    st.caption("停更於 2025 年。專注於新世代華語青年、邊緣視角與深度的社會紀實觀察。")
    st.markdown("🔗 **[前往官網探索](https://www.wainao.me/)**")

else:
    df = fetch_data(view_mode, selected_source, search_input)

    if view_mode == "✨ 全部來源總覽":
        st.subheader(f"✨ 全部來源總覽 (聚合最新 {len(df)} 篇文章)")
        st.caption("打破雜誌界限，即時串流全平台最新擷取到的文化與思想動態。")
    elif view_mode == "✍️ 最新評論":
        st.subheader(f"✍️ 最新思想與文化評論 (共 {len(df)} 篇)")
        st.caption("已自動過濾快訊快報，專注收看國內外深度長文、文獻評論與思想探討（包含 BIE別的）。")
    elif view_mode == "⚡ 文化快訊":
        st.subheader(f"⚡ 文化與藝術快訊 (共 {len(df)} 篇)")
        st.caption("聚合 WIRED.jp、CINRA、VERSE 每日高頻更新的潮流、展演與當代文化即時消息。")
    elif view_mode == "🔖 我的收藏庫":
        st.subheader(f"🔖 我的收藏庫 (共 {len(df)} 篇)")
    else:
        if selected_source != "全部來源總覽":
            st.subheader(f"🗄️ {selected_source} 存檔 (共 {len(df)} 篇)")
            st.markdown(f"🔗 **[前往該雜誌官網閱讀]({get_source_link(selected_source)})**")
        else:
            st.subheader(f"🗄️ 全部來源完整存檔 (顯示最新 500 篇)")

    st.markdown("---")

    if df.empty:
        st.info("這裡目前空空如也，找不到符合條件的文章。")
    else:
        PER_PAGE = 20
        total_pages = math.ceil(len(df) / PER_PAGE)
        if st.session_state.current_page > total_pages and total_pages > 0:
            st.session_state.current_page = total_pages
            
        start_idx = (st.session_state.current_page - 1) * PER_PAGE
        end_idx = start_idx + PER_PAGE
        
        # 渲染文章列表
        for _, row in df.iloc[start_idx:end_idx].iterrows():
            with st.container():
                st.markdown(f"#### [{row['Title']}]({row['Link']})")
                
                col_meta, col_btn = st.columns([5, 1])
                with col_meta:
                    raw_pub = str(row['Published'])
                    sort_date = row.get('SortDate')
                    
                    safe_sort_date = str(sort_date).split('T')[0] if pd.notna(sort_date) and sort_date else "未知時間"
                    display_date = f"擷取於 {safe_sort_date}" if any(k in raw_pub for k in ["最新", "Issue", "刊", "None", "nan"]) else raw_pub
                    st.caption(f"🏷️ {row['Source']} | 🕒 {display_date}")
                
                with col_btn:
                    is_bk = bool(row.get('is_bookmarked', False))
                    st.button("❤️ 已收藏" if is_bk else "🤍 收藏", key=f"btn_{row['Link']}", 
                              on_click=toggle_bookmark_db, args=(row['Link'], is_bk))
                
                # 🌟 修復引號衝突：外層使用單引號，內層 row["Image"] 改用雙引號
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
st.sidebar.caption("Monoreader Cloud v2.2 (Multi-Stream Optimized)")
