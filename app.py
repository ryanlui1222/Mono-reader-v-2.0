import streamlit as st
import pandas as pd
import json
import os
import math
import requests

# ==========================================
# 介面排版區塊與基礎設定
# ==========================================
st.set_page_config(page_title="My Culture Dashboard", layout="wide")

st.title("📚 Monoreader")

# 🔗 來源對應網址字典
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
    "The Point": "https://thepointmag.com/magazine/"
}

def get_source_link(source_name):
    if "Funambulist" in source_name: return "https://thefunambulist.net/"
    if "The Point" in source_name: return "https://thepointmag.com/magazine/"
    if "e-flux Journal" in source_name: return "https://www.e-flux.com/journal/"
    return SOURCE_URLS.get(source_name, "#")

# ==========================================
# ☁️ 雲端書籤處理中心 (JSONBin 版)
# ==========================================
if "jsonbin" in st.secrets:
    BIN_ID = st.secrets["jsonbin"]["bin_id"]
    API_KEY = st.secrets["jsonbin"]["api_key"]
    BIN_URL = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
    
    HEADERS = {
        "X-Access-Key": API_KEY,
        "Content-Type": "application/json"
    }

    def load_bookmarks():
        """從 JSONBin 雲端讀取書籤"""
        try:
            req = requests.get(BIN_URL, headers=HEADERS)
            if req.status_code == 200:
                return req.json().get("record", [])
            return []
        except Exception:
            return []

    def save_bookmarks(bookmarks_list):
        """將書籤同步寫入 JSONBin 雲端"""
        try:
            data_to_save = bookmarks_list if bookmarks_list else []
            requests.put(BIN_URL, json=data_to_save, headers=HEADERS)
        except Exception as e:
            st.error(f"書籤同步失敗：{e}")
else:
    def load_bookmarks(): return []
    def save_bookmarks(bookmarks_list): pass

# 初始化 Session State 來記住書籤
if 'bookmarks' not in st.session_state:
    st.session_state.bookmarks = load_bookmarks()

def toggle_bookmark(article_dict):
    """切換收藏狀態的觸發函數"""
    links = [b['Link'] for b in st.session_state.bookmarks]
    if article_dict['Link'] in links:
        st.session_state.bookmarks = [b for b in st.session_state.bookmarks if b['Link'] != article_dict['Link']]
    else:
        st.session_state.bookmarks.insert(0, article_dict)
    
    # 狀態更新後，立即同步到雲端
    save_bookmarks(st.session_state.bookmarks)

# ==========================================
# 資料讀取與處理
# ==========================================
@st.cache_data(ttl=900)
def load_data():
    if os.path.exists("data.json"):
        try:
            df = pd.read_json("data.json")
            def sort_key(date_str):
                if pd.isna(date_str) or "最新" in str(date_str):
                    return pd.Timestamp('1900-01-01', tz='UTC') 
                try:
                    return pd.to_datetime(date_str, utc=True)
                except:
                    return pd.Timestamp('1900-01-01', tz='UTC')
            df['SortDate'] = df['Published'].apply(sort_key)
            df = df.sort_values(by=['SortDate'], ascending=False).reset_index(drop=True)
            df = df.drop(columns=['SortDate'])
            return df
        except Exception as e:
            st.error(f"資料讀取錯誤：{e}")
            return pd.DataFrame()
    return pd.DataFrame()

news_df = load_data()

# ==========================================
# 介面渲染
# ==========================================
update_time_str = "未知"
if os.path.exists("data.json"):
    mtime = os.path.getmtime("data.json")
    update_time = pd.Timestamp(mtime, unit='s', tz='UTC').tz_convert('Asia/Taipei')
    update_time_str = update_time.strftime("%Y-%m-%d %H:%M:%S")

if not news_df.empty or st.session_state.bookmarks:
    st.sidebar.title("📂 閱讀來源")
    st.sidebar.caption(f"🔄 最後更新：{update_time_str}")
    st.sidebar.markdown("---")
    
    # 🌟 側邊欄：主選單與檔案夾邏輯
    raw_sources = news_df['Source'].unique() if not news_df.empty else []
    main_categories = set()
    
    for src in raw_sources:
        if "421 News" in src:
            main_categories.add("📁 421 News")
        else:
            main_categories.add(src)
            
    main_categories = sorted(list(main_categories), key=lambda x: x.lower().replace("📁 ", ""))
    
    # 將「🔖 我的書籤」從主選單中移除
    source_options = ["全部來源總覽"] + main_categories
    
    selected_main = st.sidebar.radio("請點選要查看的板塊：", source_options)
    
    if selected_main == "📁 421 News":
        st.sidebar.markdown("---")
        sub_options = sorted([s for s in raw_sources if "421 News" in s])
        selected_source = st.sidebar.radio("切換語言版本：", sub_options)
    else:
        selected_source = selected_main
        
    st.sidebar.markdown("---")
    
    # 🌟 獨立的書籤區塊，放置於側邊欄最下方
    st.sidebar.markdown("### 📌 個人收藏")
    view_bookmarks = st.sidebar.toggle("🔖 進入我的書籤", value=False)
    
    # 當開關被打開時，強制將顯示來源切換為書籤
    if view_bookmarks:
        selected_source = "🔖 我的書籤"
        
    st.markdown("---")

    # 決定要顯示的 DataFrame
    if selected_source == "🔖 我的書籤":
        display_df = pd.DataFrame(st.session_state.bookmarks)
        st.subheader(f"目前顯示：🔖 我的書籤 (共 {len(display_df)} 篇)")
    elif selected_source != "全部來源總覽":
        display_df = news_df[news_df['Source'] == selected_source]
        source_link = get_source_link(selected_source)
        st.subheader(f"目前顯示：{selected_source} (共 {len(display_df)} 篇)")
        st.markdown(f"🔗 **[前往 {selected_source} 官方網站閱讀更多]({source_link})**")
    else:
        display_df = news_df 
        st.subheader(f"目前顯示：全部來源總覽 (共 {len(display_df)} 篇)")
        
    st.markdown("---")

    if display_df.empty:
        st.info("這裡目前空空如也，趕快去收藏幾篇文章吧！")
    else:
        ITEMS_PER_PAGE = 20
        total_pages = math.ceil(len(display_df) / ITEMS_PER_PAGE)
        
        if total_pages > 1:
            col1, col2 = st.columns([3, 1])
            with col2:
                page_number = st.selectbox("📄 選擇頁數", range(1, total_pages + 1), index=0)
        else:
            page_number = 1
            
        start_idx = (page_number - 1) * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        page_df = display_df.iloc[start_idx:end_idx]

        # 取得已收藏清單用來變更按鈕狀態
        bookmarked_links = [b['Link'] for b in st.session_state.bookmarks]

        # 渲染文章卡片
        for index, row in page_df.iterrows():
            with st.container():
                st.markdown(f"#### [{row['Title']}]({row['Link']})")
                
                meta_col, btn_col = st.columns([5, 1])
                with meta_col:
                    st.caption(f"🏷️ {row['Source']} | 🕒 {row['Published']}")
                with btn_col:
                    is_saved = row['Link'] in bookmarked_links
                    button_label = "❌ 移除" if is_saved else "🔖 收藏"
                    st.button(button_label, key=f"btn_{row['Link']}", on_click=toggle_bookmark, args=(row.to_dict(),))
            
                if isinstance(row.get('Image'), str) and row['Image'].strip() != "":
                    if row['Image'].startswith('http'):
                        try: 
                            st.image(row['Image'], use_container_width=True)
                        except: 
                            pass
                
                st.write(row['Summary'])
                st.markdown("---")
                
        if total_pages > 1:
            st.caption(f"目前為第 {page_number} 頁，共 {total_pages} 頁")
            
else:
    st.info("目前系統正在更新資料庫中，或尚無資料，請稍後再試。")
