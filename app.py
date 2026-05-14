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

# 🔗 來源對應網址字典 (因應第四個想法)
SOURCE_URLS = {
    "Aeon 思想誌": "https://aeon.co/",
    "New Yorker, Books and Culture": "https://www.newyorker.com/culture",
    "421 News": "https://www.421.news/",
    "聯經思想空間": "https://www.linking.vision/",
    "上海書評": "https://www.thepaper.cn/list_25444",
    "藝術界": "https://www.leapleapleap.com/",
    "MIT Press Reader": "https://thereader.mitpress.mit.edu/",
    "webゲンロン": "https://webgenron.com/",
    "e-flux Journal": "https://www.e-flux.com/journal/"
}

def get_source_link(source_name):
    """處理動態名稱（如 The Funambulist 每期名稱不同）與靜態名稱的網址對應"""
    if "Funambulist" in source_name: 
        return "https://thefunambulist.net/"
    return SOURCE_URLS.get(source_name, "#")

# ==========================================
# 資料讀取與處理
# ==========================================
@st.cache_data(ttl=900)
def load_data():
    if os.path.exists("data.json"):
        try:
            df = pd.read_json("data.json")
            
            # 🕒 重新排序邏輯 (因應第一個想法)
            def sort_key(date_str):
                # 如果沒有日期，或字串中包含「最新」，給它一個極舊的年份使其沉底
                if pd.isna(date_str) or "最新" in str(date_str):
                    return pd.Timestamp('1900-01-01', tz='UTC') 
                try:
                    return pd.to_datetime(date_str, utc=True)
                except:
                    return pd.Timestamp('1900-01-01', tz='UTC')
                    
            df['SortDate'] = df['Published'].apply(sort_key)
            # 以 SortDate 降冪排序（新的在上，舊的在下，1900年的沉底）
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
# 🕒 獲取資料更新時間 (因應第三個想法)
update_time_str = "未知"
if os.path.exists("data.json"):
    mtime = os.path.getmtime("data.json")
    # 將伺服器的 UTC 時間強制轉換為亞洲/台北 (UTC+8) 時間，避免時差誤會
    update_time = pd.Timestamp(mtime, unit='s', tz='UTC').tz_convert('Asia/Taipei')
    update_time_str = update_time.strftime("%Y-%m-%d %H:%M:%S")

if not news_df.empty:
    st.sidebar.title("📂 閱讀來源")
    # 顯示全局更新時間於側邊欄最上方
    st.sidebar.caption(f"🔄 最後更新：{update_time_str}")
    st.sidebar.markdown("---")
    
    source_options = ["全部來源總覽"] + list(news_df['Source'].unique())
    selected_source = st.sidebar.radio("請點選要查看的雜誌：", source_options)
    
    if selected_source != "全部來源總覽":
        display_df = news_df[news_df['Source'] == selected_source]
        source_link = get_source_link(selected_source)
        st.subheader(f"目前顯示：{selected_source} (共 {len(display_df)} 篇)")
        # 🔗 顯示前往官方網站的跳轉連結
        st.markdown(f"🔗 **[前往 {selected_source} 官方網站閱讀更多]({source_link})**")
    else:
        # 全部來源不再限制 head(5)，改為顯示全部 (因應第二個想法)
        display_df = news_df 
        st.subheader(f"目前顯示：全部來源總覽 (共 {len(display_df)} 篇)")
        
    st.markdown("---")

    # 📄 分頁功能邏輯 (因應第二個想法)
    ITEMS_PER_PAGE = 20
    total_pages = math.ceil(len(display_df) / ITEMS_PER_PAGE)
    
    if total_pages > 1:
        # 使用左右分欄讓排版更好看，右側放置分頁選單
        col1, col2 = st.columns([3, 1])
        with col2:
            page_number = st.selectbox("📄 選擇頁數", range(1, total_pages + 1), index=0)
    else:
        page_number = 1
        
    # 計算當前頁數應該顯示的資料起訖點
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
            
    # 如果有超過一頁，在底部再次提醒目前的頁碼
    if total_pages > 1:
        st.caption(f"目前為第 {page_number} 頁，共 {total_pages} 頁")
        
else:
    st.info("目前系統正在更新資料庫中，或尚無資料，請稍後再試。")
