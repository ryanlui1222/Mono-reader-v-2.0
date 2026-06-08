import streamlit as st
import pandas as pd
import core_utils
from views import ui_components

def go_to_category(cat_name):
    st.session_state.omni_active_category = cat_name
    st.session_state.omni_page = 1 

def go_home():
    st.session_state.omni_active_category = None
    st.session_state.omni_page = 1

def render_page():
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

    # 撈取全域資料（供首頁分析封面使用）
    df_all_raw = core_utils.fetch_omni_items()
    existing_cats = core_utils.fetch_omni_categories()

    # ==========================================
    # 視圖 A：總覽首頁 (Pinterest 風格動態封面資料夾)
    # ==========================================
    if st.session_state.omni_active_category is None:
        col_desc, col_add = st.columns([3, 1])
        with col_desc: 
            st.caption("點擊下方分類資料夾，進入個人陳列室。系統會自動擷取分類最新圖片作為封面。")
        with col_add:
            with st.popover("➕ 新增靈感", use_container_width=True):
                new_cat = st.text_input("標籤分類 (如 ☕ 咖啡):", placeholder="建議格式：Emoji + 空格 + 名字")
                if existing_cats:
                    st.caption("現有標籤點擊即複製：")
                    st.markdown(" ".join([f"`{c}`" for c in existing_cats]))
                new_title = st.text_input("項目名稱 (必填):")
                new_url = st.text_input("相關連結 (選填):")
                new_image = st.text_input("圖片網址 (選填):")
                new_comment = st.text_area("筆記與推薦理由:")
                
                if st.button("💾 儲存入匣", type="primary", use_container_width=True):
                    success, msg = core_utils.add_omni_item(new_cat, new_title, new_url, new_comment, new_image)
                    if success:
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(msg)
        st.write("")

        if not existing_cats:
            st.info("📦 目前收藏匣空空如也，請建立您的第一個分類！")
        else:
            cols = st.columns(4) # 4欄流暢排列
            for idx, cat in enumerate(existing_cats):
                with cols[idx % 4]:
                    # 🔍 智慧封面搜尋：找出這一個分類中最新一筆帶有 http 圖片網址的資料
                    cover_img = None
                    if not df_all_raw.empty:
                        df_sub = df_all_raw[df_all_raw['category'] == cat]
                        for _, r in df_sub.iterrows():
                            img = r.get('image_url')
                            if pd.notna(img) and str(img).strip().startswith('http'):
                                cover_img = str(img).strip()
                                break
                    
                    # 剖析 Emoji 與 純文字
                    parts = cat.split(" ", 1)
                    icon = parts[0] if (len(parts) > 1 and len(parts[0]) <= 3) else "📁"
                    display_name = parts[1] if (len(parts) > 1 and len(parts[0]) <= 3) else cat

                    # 渲染卡片外殼
                    with st.container(border=True):
                        if cover_img:
                            # 滿版圖片封面樣式 + 暗色磨砂遮罩
                            folder_html = f"""
                            <div style="position: relative; width: 100%; aspect-ratio: 16/10; overflow: hidden; border-radius: 6px; margin-bottom: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.15);">
                                <img src="{cover_img}" style="width: 100%; height: 100%; object-fit: cover;">
                                <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.45); display: flex; align-items: center; justify-content: center; font-size: 2rem;">
                                    {icon}
                                </div>
                            </div>
                            """
                            st.markdown(folder_html, unsafe_allow_html=True)
                        else:
                            #  Graceful Fallback: 無圖片時退回超大無縫 Emoji 氣泡
                            st.markdown(f"<div style='text-align: center; font-size: 3rem; margin-bottom: 5px; padding-top:10px;'>{icon}</div>", unsafe_allow_html=True)
                        
                        st.button(f"{display_name}", key=f"nav_cat_{cat}", on_click=go_to_category, args=(cat,), use_container_width=True)

            if is_edit_mode:
                st.markdown("---")
                st.subheader("📝 全域資料庫管理")
                # 🌟 植入全域排序
                df_all_sorted = ui_components.apply_smart_sort(df_all_raw, table_name="omni_vault", context_key="all")
                ui_components.render_batch_editor(df_all_sorted, table_name="omni_vault", key_prefix="omni_all")

    # ==========================================
    # 視圖 B：單一分類陳列室 (完美 1:1 正方形卡片牆)
    # ==========================================
    else:
        active_cat = st.session_state.omni_active_category

        col_back, col_title, col_search, col_add = st.columns([1, 4, 3, 2])
        with col_back: st.button("🔙 返回", on_click=go_home, use_container_width=True)
        with col_title: st.subheader(f"📂 {active_cat}")
        with col_search: search_q = st.text_input("🔍 搜尋：", placeholder="輸入關鍵字...", label_visibility="collapsed")
        with col_add:
            with st.popover("➕ 新增至此分類", use_container_width=True):
                new_cat = st.text_input("標籤分類:", value=active_cat)
                new_title = st.text_input("項目名稱 (必填):", key="sub_add_title")
                new_url = st.text_input("相關連結 (選填):", key="sub_add_url")
                new_image = st.text_input("圖片網址 (選填):", key="sub_add_img")
                new_comment = st.text_area("筆記與推薦理由:", key="sub_add_comment")
                
                if st.button("💾 儲存", type="primary", use_container_width=True, key="sub_add_btn"):
                    success, msg = core_utils.add_omni_item(new_cat, new_title, new_url, new_comment, new_image)
                    if success:
                        st.cache_data.clear(); st.rerun()
                    else: st.error(msg)

        st.write("")

        # 撈取分類過濾後的資料
        df_omni = core_utils.fetch_omni_items(category=active_cat, search_query=search_q)
        
        # 🌟 植入全域排序
        df_omni = ui_components.apply_smart_sort(df_omni, table_name="omni_vault", context_key=active_cat)

        if is_edit_mode:
            if df_omni.empty: st.info("目前無資料可供管理。")
            else: ui_components.render_batch_editor(df_omni, table_name="omni_vault", key_prefix=f"omni_sub_{active_cat}")
        else:
            if df_omni.empty: st.info(f"「{active_cat}」目前沒有項目。")
            else:
                page_data, total_pages, current_page = ui_components.paginate_data(df_omni, per_page=12, session_key="omni_page")
                
                cols = st.columns(3)
                for idx, row in page_data.reset_index(drop=True).iterrows():
                    with cols[idx % 3]:
                        with st.container(border=True):
                            img_url = row.get('image_url')
                            if pd.notna(img_url) and str(img_url).strip().startswith("http"):
                                st.markdown(f'<img src="{img_url}" style="width: 100%; aspect-ratio: 1 / 1; object-fit: cover; border-radius: 6px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">', unsafe_allow_html=True)
                            else:
                                st.markdown(f'<div style="width: 100%; aspect-ratio: 1 / 1; background-color: #262730; border-radius: 6px; margin-bottom: 12px; display: flex; align-items: center; justify-content: center; color: #737373; font-size: 0.9rem;">無項目預覽圖</div>', unsafe_allow_html=True)
                            
                            # 標題鏈接
                            if pd.notna(row['url']) and str(row['url']).strip():
                                st.markdown(f"#### [{row['title']}]({row['url']})")
                            else:
                                st.markdown(f"#### {row['title']}")
                                
                            comment_text = str(row.get('comment', '')).strip()
                            if comment_text:
                                if len(comment_text) > 80:
                                    st.info(f"{comment_text[:80]}...")
                                    with st.expander("📖 展開完整筆記"): st.write(comment_text)
                                else: st.info(comment_text)
                                    
                            st.caption(f"📅 {str(row['added_date']).split(' ')[0]}")
                            ui_components.render_smart_popover(row, table_name="omni_vault", context="omni")
                
                ui_components.render_pagination_ui(total_pages, current_page, "omni_page")
