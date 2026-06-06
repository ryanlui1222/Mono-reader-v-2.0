import streamlit as st
import pandas as pd
import core_utils
from views import ui_components

# 定義路由跳轉函數
def go_to_category(cat_name):
    st.session_state.omni_active_category = cat_name
    st.session_state.omni_page = 1 # 重置分頁

def go_home():
    st.session_state.omni_active_category = None
    st.session_state.omni_page = 1

def render_page():
    # 初始化路由狀態 (None 代表在總覽主頁)
    if 'omni_active_category' not in st.session_state:
        st.session_state.omni_active_category = None

    # ==========================================
    # 全域頂部：標題與管理開關
    # ==========================================
    col_h1, col_h2 = st.columns([7, 3])
    with col_h1:
        st.header("🗃️ 萬物收藏匣 (Omni-Vault)")
    with col_h2:
        st.write("")
        is_edit_mode = st.toggle("🛠️ 進入試算表管理模式", key="omni_edit_mode")
        
    st.markdown("---")

    # 獲取資料庫中所有現有的大分類
    existing_cats = core_utils.fetch_omni_categories()

    # ==========================================
    # 視圖 A：總覽首頁 (顯示資料夾氣泡)
    # ==========================================
    if st.session_state.omni_active_category is None:
        
        # 首頁頂部操作區
        col_desc, col_add = st.columns([3, 1])
        with col_desc:
            st.caption("點擊下方分類資料夾，進入專屬收藏陳列室。")
        with col_add:
            with st.popover("➕ 新增靈感", use_container_width=True):
                new_cat = st.text_input("標籤分類 (如 ☕ 咖啡):", placeholder="可選現有或自創新標籤")
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

        st.write("")

        # 渲染大分類資料夾矩陣 (Grid)
        if not existing_cats:
            st.info("📦 目前收藏匣空空如也，請點擊右上方「➕ 新增靈感」建立您的第一個分類！")
        else:
            cols = st.columns(4) # 4欄排列
            for idx, cat in enumerate(existing_cats):
                with cols[idx % 4]:
                    # 打造類似資料夾卡片的視覺效果
                    with st.container(border=True):
                        st.markdown(f"<div style='text-align: center; font-size: 2.5rem; margin-bottom: 5px;'>📁</div>", unsafe_allow_html=True)
                        st.button(f"{cat}", key=f"nav_cat_{cat}", on_click=go_to_category, args=(cat,), use_container_width=True)

            # 在首頁開啟試算表模式時，顯示「全部」資料
            if is_edit_mode:
                st.markdown("---")
                st.subheader("📝 全域資料庫管理")
                df_all = core_utils.fetch_omni_items()
                ui_components.render_batch_editor(df_all, table_name="omni_vault", key_prefix="omni_all")

    # ==========================================
    # 視圖 B：單一分類陳列室 (卡片 / 試算表)
    # ==========================================
    else:
        active_cat = st.session_state.omni_active_category

        # 分類頁導航列與搜尋
        col_back, col_title, col_search, col_add = st.columns([1, 4, 3, 2])
        with col_back:
            st.button("🔙 返回", on_click=go_home, use_container_width=True)
        with col_title:
            st.subheader(f"📂 {active_cat}")
        with col_search:
            search_q = st.text_input("🔍 搜尋此分類：", placeholder="輸入關鍵字...", label_visibility="collapsed")
        with col_add:
            # 專屬新增按鈕 (自動帶入當前分類名稱)
            with st.popover("➕ 新增至此分類", use_container_width=True):
                new_cat = st.text_input("標籤分類:", value=active_cat) # 自動帶入！
                new_title = st.text_input("項目名稱 (必填):", key="sub_add_title")
                new_url = st.text_input("相關連結 (選填):", key="sub_add_url")
                new_comment = st.text_area("筆記與推薦理由:", key="sub_add_comment")
                
                if st.button("💾 儲存", type="primary", use_container_width=True, key="sub_add_btn"):
                    success, msg = core_utils.add_omni_item(new_cat, new_title, new_url, new_comment)
                    if success:
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(msg)

        st.write("")

        # 撈取專屬該分類的資料
        df_omni = core_utils.fetch_omni_items(category=active_cat, search_query=search_q)

        # 視圖分流：試算表模式 vs 浮動卡片模式
        if is_edit_mode:
            if df_omni.empty:
                st.info("目前無資料可供管理。")
            else:
                ui_components.render_batch_editor(df_omni, table_name="omni_vault", key_prefix=f"omni_sub_{active_cat}")
        else:
            if df_omni.empty:
                if search_q:
                    st.info("找不到符合關鍵字的項目。")
                else:
                    st.info(f"「{active_cat}」分類目前沒有項目，點擊上方按鈕新增吧！")
            else:
                # 套用全域分頁與卡片渲染
                page_data, total_pages, current_page = ui_components.paginate_data(df_omni, per_page=12, session_key="omni_page")
                
                cols = st.columns(3)
                for idx, row in page_data.reset_index(drop=True).iterrows():
                    with cols[idx % 3]:
                        with st.container(border=True):
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
                            ui_components.render_smart_popover(row, table_name="omni_vault", context="omni")
                
                ui_components.render_pagination_ui(total_pages, current_page, "omni_page")
