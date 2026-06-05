import streamlit as st
import math
import pandas as pd

# ==========================================
# 1. 全域分頁引擎 (Universal Pagination)
# ==========================================
def get_paginated_data(data, per_page, session_key):
    """
    接收 DataFrame 或 List，自動渲染底部頁碼選擇器，並回傳當頁應顯示的資料。
    """
    total_items = len(data)
    if total_items == 0:
        return data  # 若無資料直接回傳空集

    total_pages = max(1, math.ceil(total_items / per_page))

    # 初始化 session_state
    if session_key not in st.session_state:
        st.session_state[session_key] = 1
    
    # 邊界防護 (防止資料刪除後，當前頁碼大於總頁數)
    if st.session_state[session_key] > total_pages:
        st.session_state[session_key] = total_pages

    current_page = st.session_state[session_key]
    start_idx = (current_page - 1) * per_page
    end_idx = start_idx + per_page

    # 切割資料 (相容 DataFrame 與 List)
    if isinstance(data, pd.DataFrame):
        page_data = data.iloc[start_idx:end_idx]
    else:
        page_data = data[start_idx:end_idx]

    # 渲染底部分頁 UI
    if total_pages > 1:
        st.write("") # 留白
        col_space1, col_page, col_space2 = st.columns([1, 2, 1])
        with col_page:
            def update_page():
                st.session_state[session_key] = st.session_state[f"{session_key}_selector"]
            
            st.selectbox(
                "📄 選擇頁數：", 
                range(1, total_pages + 1), 
                index=st.session_state[session_key] - 1, 
                key=f"{session_key}_selector", 
                on_change=update_page
            )
            
    return page_data

# ==========================================
# 2. 全域網格卡片渲染 (Universal Grid Card)
# ==========================================
def render_grid_card(row):
    """
    統一渲染直立式浮動卡片 (適用於 Media Vault, 待讀書架)
    自動相容大寫 (Monoreader) 與小寫 (Biblioapp) 欄位名稱
    """
    # 智慧取值 (左邊找不到就找右邊)
    img_url = row.get('Image') or row.get('image') or row.get('poster_url')
    title = row.get('Title') or row.get('title') or "未命名"
    author = row.get('Author') or row.get('author') or row.get('year') or ""
    link = row.get('Link') or row.get('link') or "#"

    # 圖片佔位符防護
    if not img_url or (not str(img_url).startswith("http") and not str(img_url).startswith("data:")):
        img_url = "https://via.placeholder.com/150x225/2b2b2b/FFFFFF?text=No+Cover"

    # 統一 HTML/CSS 卡片結構
    html = f"""
    <div class="memoof-book" style="margin-bottom: 10px;">
        <a href="{link}" target="_blank" class="memoof-cover">
            <img src="{img_url}" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x225/2b2b2b/FFFFFF?text=No+Cover';" 
                 style="width: 100%; aspect-ratio: 2/3; object-fit: cover; border-radius: 6px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); transition: transform 0.2s;">
        </a>
        <div class="memoof-meta" style="margin-top: 8px; text-align: left;">
            <div class="memoof-title" title="{title}" style="font-weight: bold; font-size: 14px; color: #E2E8F0; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; line-height: 1.3;">{title}</div>
            <div class="memoof-author" title="{author}" style="font-size: 12px; color: #94A3B8; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{author}</div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
