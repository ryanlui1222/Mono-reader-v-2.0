import streamlit as st
import pandas as pd
import json
import os

# ==========================================
# 介面排版區塊
# ==========================================
st.set_page_config(page_title="My Culture Dashboard", layout="wide")

st.title("📚 Monoreader")
st.markdown("---")

@st.cache_data(ttl=900)  # 每 15 分鐘重新讀取一次本地的 json 即可
def load_data():
    if os.path.exists("data.json"):
        try:
            return pd.read_json("data.json")
        except Exception as e:
            st.error(f"資料讀取錯誤：{e}")
            return pd.DataFrame()
    return pd.DataFrame()

news_df = load_data()

if not news_df.empty:
    st.sidebar.title("📂 閱讀來源")
    source_options = ["全部來源"] + list(news_df['Source'].unique())
    selected_source = st.sidebar.radio("請點選要查看的雜誌：", source_options)
    
    if selected_source != "全部來源":
        display_df = news_df[news_df['Source'] == selected_source]
        st.subheader(f"目前顯示：{selected_source} (共 {len(display_df)} 篇)")
    else:
        display_df = news_df.groupby('Source').head(5).reset_index(drop=True)
        st.subheader("目前顯示：全部來源總覽")
        
    st.markdown("---")

    for index, row in display_df.iterrows():
        with st.container():
            # 手機端直接垂直排列：標題 -> 圖片 -> 摘要
            st.markdown(f"#### [{row['Title']}]({row['Link']})")
            st.caption(f"🏷️ {row['Source']} | 🕒 {row['Published']}")
        
            # 🌟 強化防護：確保圖片網址存在，且必須是 http 或 https 開頭
            if isinstance(row.get('Image'), str) and row['Image'].strip() != "":
                if row['Image'].startswith('http'):
                    try: 
                        st.image(row['Image'], use_container_width=True)
                    except: 
                        pass
            
            st.write(row['Summary'])
            st.markdown("---")
else:
    st.info("目前系統正在更新資料庫中，或尚無資料，請稍後再試。")
