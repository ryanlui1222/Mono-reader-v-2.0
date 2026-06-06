import streamlit as st
import pandas as pd
import core_utils
from views import ui_components

def render_page():
    # 頁面標題與全域開關
    col_h1, col_h2 = st.columns([7, 3])
    with col_h1:
        st.header("🗃️ 萬物收藏匣 (Omni-Vault)")
        st.caption("隨手紀錄咖啡豆、旅行地、餐廳與生活靈感。")
    with col_h2:
        st.write("")
        is_edit_mode = st.toggle("🛠️ 進入試算表管理模式", key="omni_edit_mode")
        
    st.markdown("---")

    # 獲取現有分類
    existing_cats = core_utils.fetch_omni_categories()
    
    # 1. 頂部操作區：新增與搜尋
    col_search, col_add = st.columns([3, 1])
    with col_search:
        search_q = st.text_input("🔍 搜尋收藏匣：", placeholder="關鍵字...", label_visibility="collapsed")
    with col_add:
        with st.popover("➕ 新增靈感", use_container_width=True):
            new_cat = st.text_input("標籤分類 (如 ☕ 咖啡):", placeholder="可選現有或自創新標籤")
            # 快速標籤建議
            if existing_cats:
                st.caption("現有標籤點擊即複製：")
                st.markdown(" ".join([f"`{c}`" for c in existing_cats]))
                
            new_title = st.text_input("項目名稱 (必填):")
            new_url = st.text_input("相關連結 (選填):")
            new_comment = st.text_area("筆記與推薦理由:")
            
            if st.button("💾 儲存入匣", type="primary", use_container_width=True):
                success, msg = core_utils.add_omni_item(new_cat, new_title, new_url, new_comment)
                if success:
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(msg)

    # 2. 動態分類膠囊 (Pills) 過濾器
    all_filters = ["全部"] + existing_cats
    # 支援 Streamlit 1.35+ 的 st.pills，若版本較舊可改用 radio
    try:
        selected_cat = st.pills("篩選分類", all_filters, default="全部")
    except AttributeError:
        selected_cat = st.radio("篩選分類", all_filters, horizontal=True)

    if not selected_cat: selected_cat = "全部"
    
    st.markdown("<br>", unsafe_allow_html=True)

    # 3. 撈取資料與視圖分流
    df_omni = core_utils.fetch_omni_items(category=selected_cat, search_query=search_q)

    if is_edit_mode:
        if df_omni.empty:
            st.info("目前無資料可供管理。")
        else:
            ui_components.render_batch_editor(df_omni, table_name="omni_vault", key_prefix="omni")
    else:
        if df_omni.empty:
            st.info("📦 這個分類目前空空如也，趕快新增靈感吧！")
        else:
            page_data, total_pages, current_page = ui_components.paginate_data(df_omni, per_page=15, session_key="omni_page")
            
            # 渲染卡片畫廊
            cols = st.columns(3)
            for idx, row in page_data.reset_index(drop=True).iterrows():
                with cols[idx % 3]:
                    with st.container(border=True):
                        st.markdown(f"**🏷️ {row['category']}**")
                        
                        if pd.notna(row['url']) and str(row['url']).strip():
                            st.markdown(f"### [{row['title']}]({row['url']})")
                        else:
                            st.markdown(f"### {row['title']}")
                            
                        # 備註折疊顯示
                        comment_text = str(row.get('comment', '')).strip()
                        if comment_text:
                            if len(comment_text) > 80:
                                st.info(f"{comment_text[:80]}...")
                                with st.expander("📖 展開完整筆記"): st.write(comment_text)
                            else:
                                st.info(comment_text)
                                
                        st.caption(f"📅 {str(row['added_date']).split(' ')[0]}")
                        ui_components.render_smart_popover(row, table_name="omni_vault")
            
            ui_components.render_pagination_ui(total_pages, current_page, "omni_page")
