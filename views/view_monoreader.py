import streamlit as st
import re
import pandas as pd
import core_utils
from views import ui_components

def reset_mono_page(): st.session_state.mono_page = 1
def reset_mono_res_page(): st.session_state.mono_res_page = 1

def render_page():
    if 'mono_page' not in st.session_state: st.session_state.mono_page = 1
    
    with st.sidebar:
        # 🌟 左側保留為「當前分頁搜尋」
        st.subheader("🔍 當前分頁搜尋")
        mono_local_search = st.text_input("輸入關鍵字", placeholder="過濾當前畫面...", label_visibility="collapsed", on_change=reset_mono_page)
        st.markdown("---")
        
        # 🌟 搜尋中心置於最底
        view_mode = st.radio("瀏覽模式", ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊", "🗄️ 分類存檔", "🔖 我的收藏庫", "⏳ 未來典藏", "🔍 搜尋中心"], on_change=reset_mono_page)
        st.markdown("---")

        with st.expander("📥 手動匯入外部文章", expanded=False):
            external_url = st.text_input("貼上文章網址：", placeholder="https://...")
            if st.button("解析並加入收藏庫", use_container_width=True):
                if external_url.startswith("http"):
                    with st.spinner("正在解析網頁內容..."):
                        art_data = core_utils.fetch_external_article(external_url)
                        if art_data:
                            try:
                                sql = """
                                INSERT INTO articles (Source, Title, Link, Published, Summary, Image, SortDate, is_bookmarked)
                                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                                ON CONFLICT(Link) DO UPDATE SET Title=excluded.Title, Summary=excluded.Summary, Image=excluded.Image;
                                """
                                core_utils.db.execute(sql, [art_data['Source'], art_data['Title'], art_data['Link'], art_data['Published'], art_data['Summary'], art_data['Image'], art_data['SortDate']])
                                st.cache_data.clear(); st.success("✅ 加入成功！")
                            except Exception as e: st.error(f"寫入資料庫時發生錯誤: {e}")
                        else: st.error("❌ 無法解析該網址。")
                else: st.warning("⚠️ 請輸入包含 http 的完整網址。")
        st.markdown("---")
        
        selected_source = "全部來源總覽"
        if view_mode == "🗄️ 分類存檔":
            st.subheader("選擇訂閱來源")
            FOLDER_KEYWORDS = ["The Point", "e-flux", "The Funambulist", "421 News", "TripleAmpersand"]
            main_options = []
            for src_key in sorted(core_utils.SOURCE_URLS.keys()):
                if any(k in src_key for k in FOLDER_KEYWORDS):
                    folder_name = f"📁 {src_key.split(' (')[0]}"
                    if folder_name not in main_options: main_options.append(folder_name)
                else: main_options.append(src_key)
            main_options.append("🌐 外部手動匯入")
            selected_main = st.selectbox("請選擇板塊：", ["全部來源總覽"] + main_options, on_change=reset_mono_page)

            if selected_main.startswith("📁 "):
                base_name = selected_main.replace("📁 ", "")
                res = core_utils.db.execute("SELECT DISTINCT Source FROM articles WHERE Source LIKE ?", [f"%{base_name}%"])
                raw_sources = [row[0] for row in res.rows]
                def extract_issue_number(source_str):
                    match = re.search(r'\d+', source_str)
                    return int(match.group()) if match else 0
                all_sub_sources = sorted(raw_sources, key=extract_issue_number, reverse=True)
                if all_sub_sources:
                    selected_source = st.sidebar.radio(f"{base_name} 期號/版本：", all_sub_sources, on_change=reset_mono_page)
            else: selected_source = selected_main

    col_t1, col_t2 = st.columns([7, 3])
    with col_t2:
        is_edit_mode = st.toggle("🛠️ 進入試算表管理模式", key="mono_edit_mode")

    # ==========================================
    # 🌟 獨立的搜尋中心分頁
    # ==========================================
    if view_mode == "🔍 搜尋中心":
        st.subheader("🔍 全域搜尋中心")
        global_q = st.text_input("跨板塊搜尋：", placeholder="搜尋全站文章與典藏...", key="mono_global")
        st.markdown("---")
        
        if not global_q:
            st.info("👈 請在上方輸入關鍵字，系統將為您檢索所有來源的文章與未來典藏。")
        else:
            # 搜尋文章庫 (透過 ✨ 全部來源總覽 強制跨來源)
            df_art = core_utils.fetch_data("✨ 全部來源總覽", search_query=global_q) 
            if not df_art.empty:
                st.markdown(f"#### 📄 文章與快訊 ({len(df_art)} 筆)")
                for _, row in df_art.iterrows():
                    location = "我的收藏庫" if row.get('is_bookmarked') == 1 else "存檔"
                    st.markdown(f"- **[{row.get('Title', '未命名')}]({row.get('Link', '#')})** ｜ 🏷️ {row.get('Source', '未知')} ｜ 📍 位於：`{location}`")
                st.write("")
                
            # 搜尋未來典藏
            df_future = core_utils.fetch_custom_resources("monoreader", search_query=global_q)
            if not df_future.empty:
                st.markdown(f"#### ⏳ 未來典藏庫 ({len(df_future)} 筆)")
                for _, row in df_future.iterrows():
                    st.markdown(f"- **[{row.get('title', '未命名')}]({row.get('url', '#')})** ｜ 📍 位於：`未來典藏`")
                st.write("")

            if df_art.empty and df_future.empty:
                st.warning(f"在 Monoreader 模組中，找不到包含「{global_q}」的資料。")

    # ==========================================
    # 視圖 A：未來典藏
    # ==========================================
    elif view_mode == "⏳ 未來典藏":
        st.subheader("⏳ 未來典藏 (Future Archive)")
        st.caption("記錄已停止更新，但極具歷史考據價值的邊緣文化庫。")
        with st.expander("📥 新增未來典藏網址", expanded=False):
            col1, col2 = st.columns([5, 1])
            with col1: new_res_url = st.text_input("新增網站", placeholder="請貼上網站連結...", label_visibility="collapsed", key="mono_res_input")
            with col2:
                if st.button("➕ 擷取並加入", use_container_width=True, key="mono_res_btn"):
                    if new_res_url:
                        with st.spinner("擷取標題中..."):
                            success, msg = core_utils.add_custom_resource("monoreader", new_res_url)
                            if success: st.success(msg)
                            else: st.error(msg)
        st.markdown("---")

        # 🌟 傳入局域搜尋
        df_res = core_utils.fetch_custom_resources("monoreader", search_query=mono_local_search)
        df_res = ui_components.apply_smart_sort(df_res, table_name="custom_resources", context_key="future")
        
        if is_edit_mode:
            if df_res.empty: st.info("目前無資料可供編輯。")
            else: ui_components.render_batch_editor(df_res, table_name="custom_resources", key_prefix="future")
        else:
            if df_res.empty: st.info("目前沒有相符的記錄。")
            else:
                page_data_res, total_pages, current_page = ui_components.paginate_data(df_res, per_page=15, session_key="mono_res_page")
                for _, row in page_data_res.iterrows():
                    col_link, col_action = st.columns([7, 1])
                    with col_link:
                        st.markdown(f"### {row['title']}")
                        st.markdown(f"🔗 **[前往官網探索]({row['url']})**")
                        comment_text = row.get('comment', '')
                        if pd.notna(comment_text) and str(comment_text).strip() != "":
                            st.info(f"{comment_text}")
                    with col_action:
                        ui_components.render_smart_popover(row, table_name="custom_resources")
                    st.divider()
                ui_components.render_pagination_ui(total_pages, current_page, "mono_res_page")

    # ==========================================
    # 視圖 B：文化文章主體
    # ==========================================
    else:
        if view_mode == "✨ 全部來源總覽":
            st.subheader("✨ 全部來源總覽")
            st.caption("打破雜誌界限，即時串流全平台最新擷取到的文化與思想動態。")
        elif view_mode == "✍️ 最新評論":
            st.subheader("✍️ 最新思想與文化評論")
            st.caption("已自動過濾快訊，專注收看國內外深度長文與思想探討。")
        elif view_mode == "⚡ 文化快訊":
            st.subheader("⚡ 文化與藝術快訊")
            st.caption("聚合每日高頻更新的即時藝文消息。")
        elif view_mode == "🔖 我的收藏庫":
            st.subheader("🔖 我的收藏庫")
        else:
            if selected_source != "全部來源總覽":
                st.subheader(f"🗄️ {selected_source} 存檔")
                link = core_utils.get_source_link(selected_source)
                if link != "#": st.markdown(f"🔗 **[前往該雜誌官網閱讀]({link})**")
            else:
                st.subheader("🗄️ 全部來源完整存檔 (顯示最新 500 篇)")
        
        st.markdown("---")

        # 🌟 傳入局域搜尋
        df = core_utils.fetch_data(view_mode, selected_source, search_query=mono_local_search)
        df = ui_components.apply_smart_sort(df, table_name="articles", context_key=view_mode)

        if is_edit_mode:
            if df.empty: st.info("目前無資料可供編輯。")
            else: ui_components.render_batch_editor(df, table_name="articles", key_prefix="articles")
        else:
            if df.empty:
                st.info("暫無符合條件的文章。")
            else:
                page_data, total_pages, current_page = ui_components.paginate_data(df, per_page=20, session_key="mono_page")
                for _, row in page_data.iterrows():
                    with st.container():
                        st.markdown(f"#### [{row['Title']}]({row['Link']})")
                        col_meta, col_btn = st.columns([7, 1])
                        with col_meta:
                            raw_pub = str(row['Published'])
                            sort_date = row.get('SortDate')
                            safe_sort_date = str(sort_date).split('T')[0] if pd.notna(sort_date) and sort_date else "未知時間"
                            display_date = f"擷取於 {safe_sort_date}" if any(k in raw_pub for k in ["最新", "Issue", "刊", "None", "nan", "歷史歸檔"]) else raw_pub
                            st.caption(f"🏷️ {row['Source']} | 🕒 {display_date}")
                        
                        with col_btn:
                            ui_components.render_smart_popover(row, table_name="articles")
                    
                    if row['Image'] and str(row['Image']).startswith('http'):
                        img_html = f'<img src="{row["Image"]}" style="width:100%; max-width:800px; border-radius:8px; display:block; margin-bottom:15px; object-fit: cover;" loading="lazy">'
                        st.markdown(img_html, unsafe_allow_html=True)
                    st.write(row['Summary'])
                    st.markdown("---")

                ui_components.render_pagination_ui(total_pages, current_page, "mono_page")
