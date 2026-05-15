import streamlit as st
import pandas as pd
from supabase import create_client, Client
import math
from datetime import datetime, timedelta
import re

# ==========================================
# 1. 介面基礎設定與路徑定義
# ==========================================
st.set_page_config(page_title="Monoreader Cloud", layout="wide", initial_sidebar_state="expanded")

# 🔗 官方來源網址對應
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
    # 取得基礎名稱以查找對應網址 (例如 "The Point (Issue 35)" -> "The Point")
    base_name = source_name.split(" (")[0]
    return SOURCE_URLS.get(base_name, "#")

# ==========================================
# 2. 雲端資料庫連線與資料操作
# ==========================================
@st.cache_resource
def init_connection():
    """建立 Supabase 連線"""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

@st.cache_data(ttl=600)
def fetch_data(view_mode, source_filter="全部來源總覽", search_query=""):
    """
    核心資料抓取邏輯
    """
    query = supabase.table('articles').select("*")
    
    # --- 邏輯 A: 處理瀏覽模式 ---
    if view_mode == "🔥 今日最新":
        # 僅抓取過去 24 小時內「擷取」到的文章 (SortDate)
        time_threshold = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        query = query.gte("SortDate", time_threshold)
    
    elif view_mode == "🔖 我的收藏庫":
        query = query.eq("is_bookmarked", True)
    
    # --- 邏輯 B: 處理分類存檔的來源過濾 ---
    # 只有在非「今日最新」模式下，來源過濾才會生效
    if view_mode != "🔥 今日最新" and source_filter != "全部來源總覽":
        query = query.eq("Source", source_filter)
             
    # --- 邏輯 C: 處理全文搜尋 ---
    if search_query:
        query = query.or_(f'Title.ilike.%{search_query}%,Summary.ilike.%{search_query}%')
        
    # 預設依時間排序，並限制 500 筆以確保效能
    res = query.order("SortDate", desc=True).limit(500).execute()
    return pd.DataFrame(res.data)

def toggle_bookmark_db(link, current_state):
    """切換收藏狀態"""
    try:
        supabase.table('articles').update({"is_bookmarked": not current_state}).eq("Link", link).execute()
        st.cache_data.clear() # 強制刷新快取
        st.toast("書籤狀態已更新！")
    except Exception as e:
        st.error(f"操作失敗: {e}")

# ==========================================
# 3. 介面渲染：側邊欄 (Sidebar)
# ==========================================
st.sidebar.title("📚 Monoreader")

# --- 搜尋功能 ---
search_input = st.sidebar.text_input("🔍 全文搜尋", placeholder="文章、作者或關鍵字...")
st.sidebar.markdown("---")

# --- 核心模式選擇 ---
view_mode = st.sidebar.radio("瀏覽模式", ["🔥 今日最新", "🗄️ 分類存檔", "🔖 我的收藏庫"])
st.sidebar.markdown("---")

# --- 分類存檔邏輯 (僅在分類模式顯示) ---
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
            
    selected_main = st.sidebar.selectbox("請選擇板塊：", ["全部來源總覽"] + main_options)

    # 動態次選單處理
    if selected_main.startswith("📁 "):
        base_name = selected_main.replace("📁 ", "")
        res = supabase.table('articles').select('Source').ilike('Source', f'%{base_name}%').execute()
        
        # 1. 先抓出所有不重複的 Source
        raw_sources = list(set([r['Source'] for r in res.data]))
        
        # 2. 智慧排序邏輯：提取括號中的數字進行絕對大小排序
        def extract_issue_number(source_str):
            match = re.search(r'\d+', source_str)
            return int(match.group()) if match else 0
            
        all_sub_sources = sorted(raw_sources, key=extract_issue_number, reverse=True)
        
        if all_sub_sources:
            selected_source = st.sidebar.radio(f"{base_name} 期號/版本：", all_sub_sources)
    else:
        selected_source = selected_main

# ==========================================
# 4. 介面渲染：主畫面 (Main View)
# ==========================================
df = fetch_data(view_mode, selected_source, search_input)

# 顯示頁面標題與小工具
if view_mode == "🔥 今日最新":
    st.subheader(f"🔥 今日最新文章 (過去 24 小時內，共 {len(df)} 篇)")
    st.caption("自動顯示每日爬蟲擷取到的最新內容。")
elif view_mode == "🔖 我的收藏庫":
    st.subheader(f"🔖 我的收藏庫 (共 {len(df)} 篇)")
else:
    if selected_source != "全部來源總覽":
        st.subheader(f"🗄️ {selected_source} 存檔 (共 {len(df)} 篇)")
        st.markdown(f"🔗 **[前往該雜誌官網閱讀]({get_source_link(selected_source)})**")
    else:
        st.subheader(f"🗄️ 全部來源完整存檔 (顯示最新 500 篇)")

st.markdown("---")

# 檢查是否有資料
if df.empty:
    if search_input: st.info("找不到符合關鍵字的文章。")
    elif view_mode == "🔥 今日最新": st.info("今日暫無新文章，請待下次爬蟲執行或查看分類存檔。")
    else: st.info("這裡目前空空如也。")
else:
    # --- 分頁系統 (Pagination) ---
    PER_PAGE = 20
    total_pages = math.ceil(len(df) / PER_PAGE)
    
    if total_pages > 1:
        col_p1, col_p2 = st.columns([4, 1])
        with col_p2:
            page = st.selectbox("📄 選擇頁數", range(1, total_pages + 1))
    else:
        page = 1
    
    start_idx = (page - 1) * PER_PAGE
    end_idx = start_idx + PER_PAGE
    
    # --- 渲染文章列表 ---
    for _, row in df.iloc[start_idx:end_idx].iterrows():
        with st.container():
            st.markdown(f"#### [{row['Title']}]({row['Link']})")
            
            col_meta, col_btn = st.columns([5, 1])
            with col_meta:
                raw_pub = str(row['Published'])
                sort_date = row.get('SortDate')
                
                # 防呆機制：如果資料庫裡極端情況下仍是空值
                if pd.isna(sort_date) or sort_date is None:
                    safe_sort_date = "未知時間"
                else:
                    safe_sort_date = str(sort_date).split('T')[0]
                
                # 判斷是否需要輔助顯示「擷取時間」
                if any(k in raw_pub for k in ["最新", "Issue", "刊", "None", "nan"]):
                    display_date = f"擷取於 {safe_sort_date}"
                else:
                    display_date = raw_pub
                
                st.caption(f"🏷️ {row['Source']} | 🕒 {display_date}")
            
            with col_btn:
                is_bk = bool(row.get('is_bookmarked', False))
                st.button("❤️ 已收藏" if is_bk else "🤍 收藏", key=f"btn_{row['Link']}", 
                          on_click=toggle_bookmark_db, args=(row['Link'], is_bk))
            
            # 圖片顯示與錯誤捕捉
            if row['Image'] and str(row['Image']).startswith('http'):
                try: 
                    st.image(row['Image'], use_container_width=True)
                except: 
                    pass
                
            st.write(row['Summary'])
            st.markdown("---")

    if total_pages > 1:
        st.caption(f"目前顯示第 {page} 頁，共 {total_pages} 頁")

# 底部狀態列
st.sidebar.markdown("---")
st.sidebar.caption("Monoreader Cloud v2.0")
