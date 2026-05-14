import streamlit as st
import pandas as pd
import json
import os
import math

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
    """處理動態名稱（如 The Funambulist 每期名稱不同）與靜態名稱的網址對應"""
    if "Funambulist" in source_name: 
        return "https://thefunambulist.net/"
    if "The Point" in source_name:
        return "https://thepointmag.com/magazine/"
    if "e-flux Journal" in source_name:
        return "https://www.e-flux.com/journal/"
    return SOURCE_URLS.get(source_name, "#")

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

if not news_df.empty:
    st.sidebar.title("📂 閱讀來源")
    st.sidebar.caption(f"🔄 最後更新：{update_time_str}")
    st.sidebar.markdown("---")
    
    # ==========================================
    # 🌟 側邊欄：檔案夾邏輯與字母排序
    # ==========================================
    raw_sources = news_df['Source'].unique()
    main_categories = set()
    
    # 建立主目錄 (將 421 歸納為資料夾)
    for src in raw_sources:
        if "421 News" in src:
            main_categories.add("📁 421 News")
        else:
            main_categories.add(src)
            
    # 字母 A-Z 排序 (忽略大小寫與圖示字元)
    main_categories = sorted(list(main_categories), key=lambda x: x.lower().replace("📁 ", ""))
    source_options = ["全部來源總覽"] + main_categories
    
    # 渲染主選單
    selected_main = st.sidebar.radio("請點選要查看的雜誌：", source_options)
    
    # 若選擇資料夾，展開次選單
    if selected_main == "📁 421 News":
        st.sidebar.markdown("---")
        sub_options = sorted([s for s in raw_sources if "421 News" in s])
        selected_source = st.sidebar.radio("切換語言版本：", sub_options)
    else:
        selected_source = selected_main
        
    st.markdown("---")

    # ==========================================
    # 渲染文章主體
    # ==========================================
    if selected_source != "全部來源總覽":
        display_df = news_df[news_df['Source'] == selected_source]
        source_link = get_source_link(selected_source)
        st.subheader(f"目前顯示：{selected_source} (共 {len(display_df)} 篇)")
        st.markdown(f"🔗 **[前往 {selected_source} 官方網站閱讀更多]({source_link})**")
    else:
        display_df = news_df 
        st.subheader(f"目前顯示：全部來源總覽 (共 {len(display_df)} 篇)")
        
    st.markdown("---")

    # 分頁功能邏輯
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

    # 渲染文章卡片
    for index, row in page_df.iterrows():
        with st.container():
            st.markdown(f"#### [{row['Title']}]({row['Link']})")
            st.caption(f"🏷️ {row['Source']} | 🕒 {row['Published']}")
        
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
