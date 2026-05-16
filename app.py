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

selected_source
