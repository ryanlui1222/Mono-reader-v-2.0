import streamlit as st
import pandas as pd
from supabase import create_client, Client
import math
from datetime import datetime, timedelta

# ==========================================
# 1. 介面基礎設定
# ==========================================
st.set_page_config(page_title="Monoreader Cloud", layout="wide", initial_sidebar_state="expanded")

# 🔗 官方來源網址
SOURCE_URLS = {
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
    "The Funambulist": "https://thefunambulist.net/"
}

def get_source_link(source_name):
    base_name = source_name.split(" (")[0]
    return SOURCE_URLS.get(base_name, "#")

# ==========================================
# 2. 雲端資料庫連線
# ==========================================
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

@st.cache_data(ttl=600)
def fetch_data(view_mode, source_filter="全部來源總覽", search_query=""):
    query = supabase.table('articles').select("*")
    
    # --- 邏輯 1: 處理瀏覽模式 ---
    if view_mode == "🔥 今日最新":
        # 抓取過去 24 小時的文章
        time_threshold = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        query = query.gte("SortDate", time_threshold)
    
    elif view_mode == "🔖 我的收藏庫":
        query = query.eq("is_bookmarked", True)
    
    # --- 邏輯 2: 處理來源過濾 (僅在非「今日最新」模式下生效) ---
    if view_mode != "🔥 今日最新" and source_filter != "全部來源總覽":
        query = query.eq("Source", source_filter)
             
    # --- 邏輯 3: 全文搜尋 ---
    if search_query:
        query = query.or_(f'Title.ilike.%{search_query}%,Summary.ilike.%{search_query}%')
        
    res = query.order("SortDate", desc=True).limit(500).execute()
    return pd.DataFrame(res.data)

def toggle_bookmark_db(link, current_state):
    try:
        supabase.table('articles').update({"is_bookmarked": not current_state}).eq("Link", link).execute()
        st.cache_data.clear()
        st.toast("書籤狀態已更新")
    except Exception as e:
        st.error(f"操作失敗: {e}")

# ==========================================
# 3. 側邊欄渲染 (Sidebar)
# ==========================================
st.sidebar.title("📚 Monoreader")

# --- 搜尋框 ---
search_input = st.sidebar.text_input("🔍 雲端全文搜尋", placeholder="關鍵字或作者...")
st.sidebar.markdown("---")

# --- 核心模式切換 ---
view_mode = st.sidebar.radio("瀏覽模式", ["🔥 今日最新", "🗄️ 分類存檔", "🔖 我的收藏庫"])
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
            
    selected_main = st.sidebar.selectbox("請選擇版塊：", ["全部來源總覽"] + main_options)

    if selected_main.startswith("📁 "):
        base_name = selected_main.replace("📁 ", "")
        res = supabase.table('articles').select('Source').ilike('Source', f'%{base_name}%').execute()
        all_sub_sources = sorted(list(set([r['Source'] for r in res.data])), reverse=True)
        if all_sub_sources:
            selected_source = st.sidebar.radio(f"{base_name} 期號：", all_sub_sources)
    else:
        selected_source = selected_main

# ==========================================
# 4. 主畫面渲染
# ==========================================
df = fetch_data(view_mode, selected_source, search_input)

# 顯示標題
if view_mode == "🔥 今日最新":
    st.subheader(f"🔥 今日最新文章 (過去 24 小時，共 {len(df)} 篇)")
    st.caption("這裡僅顯示最新抓取的內容，保持閱讀的新鮮感。")
elif view_mode == "🔖 我的收藏庫":
    st.subheader(f"🔖 我的收藏庫 (共 {len(df)} 篇)")
else:
    if selected_source != "全部來源總覽":
        st.subheader(f"🗄️ {selected_source} 存檔 (共 {len(df)} 篇)")
        st.markdown(f"🔗 **[前往官網]({get_source_link(selected_source)})**")
    else:
        st.subheader(f"🗄️ 全部來源完整存檔 (顯示最新 500 篇)")

st.markdown("---")

if df.empty:
    if search_input: st.info("找不到符合關鍵字的文章。")
    elif view_mode == "🔥 今日最新": st.info("過去 24 小時內暫無新抓取的文章。")
    else: st.info("這裡目前空空如也。")
else:
    # 分頁
    PER_PAGE = 20
    total_pages = math.ceil(len(df) / PER_PAGE)
    page = st.selectbox("📄 選擇頁數", range(1, total_pages + 1)) if total_pages > 1 else 1
    
    for _, row in df.iloc[(page-1)*PER_PAGE : page*PER_PAGE].iterrows():
        with st.container():
            st.markdown(f"#### [{row['Title']}]({row['Link']})")
            col_meta, col_btn = st.columns([5, 1])
            with col_meta:
                clean_date = str(row['Published']).split('T')[0] if pd.notna(row['Published']) else "最新"
                st.caption(f"🏷️ {row['Source']} | 🕒 {clean_date}")
            with col_btn:
                is_bk = bool(row.get('is_bookmarked', False))
                st.button("❤️ 已收藏" if is_bk else "🤍 收藏", key=f"btn_{row['Link']}", 
                          on_click=toggle_bookmark_db, args=(row['Link'], is_bk))
            
            if row['Image'] and str(row['Image']).startswith('http'):
                try: st.image(row['Image'], use_container_width=True)
                except: pass
            st.write(row['Summary'])
            st.markdown("---")
