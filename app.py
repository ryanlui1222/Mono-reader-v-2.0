import streamlit as st
import pandas as pd
from supabase import create_client, Client
import math

# ==========================================
# 1. 介面排版區塊與基礎設定
# ==========================================
st.set_page_config(page_title="Monoreader Cloud", layout="wide", initial_sidebar_state="expanded")
st.title("📚 Monoreader Cloud")

# 🔗 官方來源網址對應 (用於跳轉連結)
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
    # 處理帶有期號的來源名稱，提取主名稱以查找 URL
    base_name = source_name.split(" (")[0]
    return SOURCE_URLS.get(base_name, "#")

# ==========================================
# 2. 雲端資料庫連線與資料操作
# ==========================================
@st.cache_resource
def init_connection():
    """初始化 Supabase 連線"""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

@st.cache_data(ttl=600)
def fetch_data(source_filter="全部來源總覽", search_query="", show_bookmarks=False):
    """
    從 Supabase 抓取資料
    - source_filter: 具體的來源名稱 (包含期號)
    - search_query: 全文搜尋關鍵字
    - show_bookmarks: 是否僅顯示收藏文章
    """
    query = supabase.table('articles').select("*")
    
    # 1. 處理書籤模式
    if show_bookmarks:
        query = query.eq("is_bookmarked", True)
    # 2. 處理特定來源過濾 (精確匹配，避免期號堆疊)
    elif source_filter != "全部來源總覽":
        query = query.eq("Source", source_filter)
             
    # 3. 全文搜尋邏輯 (模糊比對標題或摘要)
    if search_query:
        query = query.or_(f'Title.ilike.%{search_query}%,Summary.ilike.%{search_query}%')
        
    # 依時間排序並限制前 500 筆，確保效能
    res = query.order("SortDate", desc=True).limit(500).execute()
    return pd.DataFrame(res.data)

def toggle_bookmark_db(link, current_state):
    """更新資料庫中的書籤狀態"""
    new_state = not current_state
    try:
        supabase.table('articles').update({"is_bookmarked": new_state}).eq("Link", link).execute()
        st.cache_data.clear() # 更新後清除快取以刷新介面
        st.toast("❤️ 已收藏" if new_state else "🤍 已移除收藏")
    except Exception as e:
        st.error(f"操作失敗: {e}")

# ==========================================
# 3. 介面渲染：側邊欄 (Sidebar)
# ==========================================
st.sidebar.title("📂 導覽與搜尋")

# --- 搜尋功能 ---
search_input = st.sidebar.text_input("🔍 全文搜尋", placeholder="輸入關鍵字或作者...")
st.sidebar.markdown("---")

# --- 瀏覽模式 ---
view_mode = st.sidebar.radio("瀏覽模式", ["最新文章", "🔖 我的收藏庫"])
st.sidebar.markdown("---")

# --- 來源選單與動態期號資料夾 ---
if view_mode == "最新文章":
    st.sidebar.subheader("閱讀版塊")
    
    # 定義哪些來源需要「資料夾化」(處理期號)
    FOLDER_KEYWORDS = ["The Point", "e-flux", "The Funambulist", "421 News"]
    
    main_options = []
    for src_key in sorted(SOURCE_URLS.keys()):
        if any(k in src_key for k in FOLDER_KEYWORDS):
            # 統一主名稱，例如 "The Point (Issue 35)" -> "📁 The Point"
            folder_name = f"📁 {src_key.split(' (')[0]}"
            if folder_name not in main_options:
                main_options.append(folder_name)
        else:
            main_options.append(src_key)
            
    source_menu = ["全部來源總覽"] + main_options
    selected_main = st.sidebar.selectbox("請選擇來源：", source_menu)

    # --- 動態次選單：處理期號 / 分類 ---
    if selected_main.startswith("📁 "):
        st.sidebar.markdown("---")
        base_name = selected_main.replace("📁 ", "")
        
        # 向資料庫查詢該品牌下現有的所有具體 Source 標籤
        res = supabase.table('articles').select('Source').ilike('Source', f'%{base_name}%').execute()
        all_sub_sources = sorted(list(set([r['Source'] for r in res.data])), reverse=True)
        
        if all_sub_sources:
            selected_source = st.sidebar.radio(f"{base_name} 期號選擇：", all_sub_sources)
        else:
            selected_source = selected_main # 若無資料則退回主名稱
    else:
        selected_source = selected_main
else:
    # 書籤模式下不顯示來源選單
    selected_source = "🔖 我的書籤"

# ==========================================
# 4. 介面渲染：主畫面 (Main Content)
# ==========================================
st.markdown("---")

# 獲取資料
is_bookmark_view = (view_mode == "🔖 我的收藏庫")
df = fetch_data(selected_source, search_input, is_bookmark_view)

# 標題與網址連結
if is_bookmark_view:
    st.subheader(f"目前顯示：🔖 我的收藏庫 (共 {len(df)} 篇)")
elif selected_source != "全部來源總覽":
    link = get_source_link(selected_source)
    st.subheader(f"目前顯示：{selected_source} (共 {len(df)} 篇)")
    st.markdown(f"🔗 **[前往該雜誌官網閱讀更多]({link})**")
else:
    st.subheader(f"目前顯示：全部來源總覽 (共 {len(df)} 篇)")

st.markdown("---")

if df.empty:
    st.info("尚無符合條件的文章。如果是新設定的資料庫，請先執行一次爬蟲。")
else:
    # 分頁處理
    PER_PAGE = 20
    total_pages = math.ceil(len(df) / PER_PAGE)
    page = st.selectbox("📄 頁數", range(1, total_pages + 1)) if total_pages > 1 else 1
    
    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    
    for _, row in df.iloc[start:end].iterrows():
        with st.container():
            st.markdown(f"#### [{row['Title']}]({row['Link']})")
            
            col_meta, col_btn = st.columns([5, 1])
            with col_meta:
                # 簡化日期顯示
                clean_date = str(row['Published']).split('T')[0] if pd.notna(row['Published']) else "最新"
                st.caption(f"🏷️ {row['Source']} | 🕒 {clean_date}")
            
            with col_btn:
                is_bk = bool(row.get('is_bookmarked', False))
                label = "❤️ 已收藏" if is_bk else "🤍 收藏"
                st.button(label, key=f"btn_{row['Link']}", on_click=toggle_bookmark_db, args=(row['Link'], is_bk))
            
            # 圖片處理
            if row['Image'] and str(row['Image']).startswith('http'):
                try: st.image(row['Image'], use_container_width=True)
                except: pass
                
            st.write(row['Summary'])
            st.markdown("---")

    if total_pages > 1:
        st.caption(f"第 {page} 頁 / 共 {total_pages} 頁")
