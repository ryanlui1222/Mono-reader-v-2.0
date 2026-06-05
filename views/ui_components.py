import streamlit as st
import math
import pandas as pd

# ==========================================
# 1. 全域分頁引擎 (Universal Pagination) - 兩階段版
# ==========================================
def paginate_data(data, per_page, session_key):
    """
    第一階段：接收 DataFrame 或 List，處理頁碼邏輯並回傳切割後的當頁資料。
    不渲染任何 UI。
    """
    total_items = len(data)
    if total_items == 0:
        return data, 0, 1

    total_pages = max(1, math.ceil(total_items / per_page))

    # 初始化 session_state
    if session_key not in st.session_state:
        st.session_state[session_key] = 1
    
    # 邊界防護
    if st.session_state[session_key] > total_pages:
        st.session_state[session_key] = total_pages

    current_page = st.session_state[session_key]
    start_idx = (current_page - 1) * per_page
    end_idx = start_idx + per_page

    # 切割資料
    if isinstance(data, pd.DataFrame):
        page_data = data.iloc[start_idx:end_idx]
    else:
        page_data = data[start_idx:end_idx]

    return page_data, total_pages, current_page

def render_pagination_ui(total_pages, current_page, session_key):
    """
    第二階段：在列表底部渲染包含「上一頁、選單、下一頁」的分頁控制器。
    """
    if total_pages <= 1:
        return

    st.write("") # 留白
    st.markdown("---")
    
    col_prev, col_page, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if st.button("⬅️ 上一頁", disabled=(current_page <= 1), key=f"prev_{session_key}", use_container_width=True):
            st.session_state[session_key] -= 1
            st.rerun()
            
    with col_page:
        def update_page():
            st.session_state[session_key] = st.session_state[f"{session_key}_selector"]
        
        st.selectbox(
            "📄 選擇頁數：", 
            range(1, total_pages + 1), 
            index=current_page - 1, 
            key=f"{session_key}_selector", 
            on_change=update_page,
            label_visibility="collapsed" # 隱藏標籤讓排版更緊湊
        )
        
    with col_next:
        if st.button("下一頁 ➡️", disabled=(current_page >= total_pages), key=f"next_{session_key}", use_container_width=True):
            st.session_state[session_key] += 1
            st.rerun()

# ==========================================
# 2. 全域網格卡片渲染 (Universal Grid Card)
# ==========================================
def render_grid_card(row):
    """
    統一渲染直立式浮動卡片 (適用於 Media Vault, 待讀書架)
    自動相容大寫 (Monoreader) 與小寫 (Biblioapp) 欄位名稱
    """
    img_url = row.get('Image') or row.get('image') or row.get('poster_url')
    title = row.get('Title') or row.get('title') or "未命名"
    author = row.get('Author') or row.get('author') or row.get('year') or ""
    link = row.get('Link') or row.get('link') or "#"

    if not img_url or (not str(img_url).startswith("http") and not str(img_url).startswith("data:")):
        img_url = "https://via.placeholder.com/150x225/2b2b2b/FFFFFF?text=No+Cover"

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
