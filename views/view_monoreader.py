import streamlit as st
import math
import re
import pandas as pd
import core_utils

def reset_mono_page(): st.session_state.mono_page = 1
def update_mono_page(): 
    if "mono_page_selector" in st.session_state: st.session_state.mono_page = st.session_state.mono_page_selector

def render_page():
    if 'mono_page' not in st.session_state: st.session_state.mono_page = 1
    
    st.sidebar.subheader("文章篩選")
    search_input = st.sidebar.text_input("🔍 全文搜尋", placeholder="文章、作者或關鍵字...", on_change=reset_mono_page)
    st.sidebar.markdown("---")
    view_mode = st.sidebar.radio("瀏覽模式", ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊", "🗄️ 分類存檔", "🔖 我的收藏庫", "⏳ 未來典藏"], on_change=reset_mono_page)
    st.sidebar.markdown("---")

    with st.sidebar.expander("📥 手動匯入外部文章", expanded=False):
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

    st.sidebar.markdown("---")
    
    selected_source = "全部來源總覽"
    if view_mode == "🗄️ 分類存檔":
        st.sidebar.subheader("選擇訂閱來源")
        FOLDER_KEYWORDS = ["The Point", "e-flux", "The Funambulist", "421 News", "TripleAmpersand"]
        main_options = []
        for src_key in sorted(core_utils.SOURCE_URLS.keys()):
            if any(k in src_key for k in FOLDER_KEYWORDS):
                folder_name = f"📁 {src_key.split(' (')[0]}"
                if folder_name not in main_options: main_options.append(folder_name)
            else: main_options.append(src_key)
        main_options.append("🌐 外部手動匯入")
        selected_main = st.sidebar.selectbox("請選擇板塊：", ["全部來源總覽"] + main_options, on_change=reset_mono_page)

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
        else:
            selected_source = selected_main

    if view_mode == "⏳ 未來典藏":
        st.subheader("⏳ 未來典藏 (Future Archive)")
        st.markdown("這裡記錄了已停止更新，但極具歷史考據與思想回溯價值的邊緣文化與次文化資料庫。")
        
        with st.container():
            col1, col2 = st.columns([5, 1])
            with col1:
                new_res_url = st.text_input("新增網站", placeholder="請貼上網站連結...", label_visibility="collapsed", key="mono_res_input")
            with col2:
                if st.button("➕ 擷取並加入", use_container_width=True, key="mono_res_btn"):
                    if new_res_url:
                        with st.spinner("擷取標題中..."):
                            success, msg = core_utils.add_custom_resource("monoreader", new_res_url)
                            if success: st.success(msg)
                            else: st.error(msg)
        st.markdown("---")

        df_res = core_utils.fetch_custom_resources("monoreader")
        if df_res.empty:
            st.info("目前沒有任何記錄。請在上方輸入網址。")
        else:
            for _, row in df_res.iterrows():
                col_link, col_action = st.columns([7, 1])
                with col_link:
                    st.markdown(f"### {row['title']}")
                    st.markdown(f"🔗 **[前往官網探索]({row['url']})**")
                    comment_text = row.get('comment', '')
                    if pd.notna(comment_text) and str(comment_text).strip() != "":
                        st.info(f"{comment_text}")
                        
                with col_action:
                    with st.popover("⚙️ 管理"):
                        edit_title = st.text_input("修改顯示名稱：", value=row['title'], key=f"edit_{row['id']}")
                        current_comment = row.get('comment', '') if pd.notna(row.get('comment')) else ""
                        edit_comment = st.text_area("編輯網站功能/內容介紹：", value=current_comment, key=f"edit_cmt_{row['id']}", height=100)
                        st.button("💾 儲存修改", key=f"save_{row['id']}", on_click=core_utils.update_custom_resource, args=(row['id'], edit_title, edit_comment), use_container_width=True)
                        st.button("🗑️ 刪除網站", key=f"del_{row['id']}", on_click=core_utils.delete_custom_resource, args=(row['id'],), type="primary", use_container_width=True)
                st.divider()

    else:
        df = core_utils.fetch_data(view_mode, selected_source, search_input)

        if view_mode == "✨ 全部來源總覽":
            st.subheader(f"✨ 全部來源總覽 (過去 24 小時，共 {len(df)} 篇文章)")
            st.caption("打破雜誌界限，即時串流全平台最新擷取到的文化與思想動態。")
        elif view_mode == "✍️ 最新評論":
            st.subheader(f"✍️ 最新思想與文化評論 (過去 24 小時，共 {len(df)} 篇)")
            st.caption("已自動過濾快訊快報，專注收看國內外深度長文、文獻評論與思想探討。")
        elif view_mode == "⚡ 文化快訊":
            st.subheader(f"⚡ 文化與藝術快訊 (過去 24 小時，共 {len(df)} 篇)")
            st.caption("聚合 WIRED.jp、CINRA、VERSE、界面文化、Radii 每日高頻更新的即時消息。")
        elif view_mode == "🔖 我的收藏庫":
            st.subheader(f"🔖 我的收藏庫 (共 {len(df)} 篇)")
        else:
            if selected_source != "全部來源總覽":
                st.subheader(f"🗄️ {selected_source} 存檔 (共 {len(df)} 篇)")
                link = core_utils.get_source_link(selected_source)
                if link != "#": st.markdown(f"🔗 **[前往該雜誌官網閱讀]({link})**")
            else:
                st.subheader(f"🗄️ 全部來源完整存檔 (顯示最新 500 篇)")

        st.markdown("---")

        if df.empty:
            if search_input: st.info("找不到符合關鍵字的文章。")
            else: st.info("暫無符合條件的新文章。")
        else:
            PER_PAGE = 20
            total_pages = math.ceil(len(df) / PER_PAGE)
            if st.session_state.mono_page > total_pages and total_pages > 0: st.session_state.mono_page = total_pages
            start_idx = (st.session_state.mono_page - 1) * PER_PAGE
            
            for _, row in df.iloc[start_idx:start_idx + PER_PAGE].iterrows():
                with st.container():
                    st.markdown(f"#### [{row['Title']}]({row['Link']})")
                    col_meta, col_btn1, col_btn2 = st.columns([6, 1, 1])
                    with col_meta:
                        raw_pub = str(row['Published'])
                        sort_date = row.get('SortDate')
                        safe_sort_date = str(sort_date).split('T')[0] if pd.notna(sort_date) and sort_date else "未知時間"
                        display_date = f"擷取於 {safe_sort_date}" if any(k in raw_pub for k in ["最新", "Issue", "刊", "None", "nan", "歷史歸檔"]) else raw_pub
                        st.caption(f"🏷️ {row['Source']} | 🕒 {display_date}")
                    
                    is_bk = bool(row.get('is_bookmarked', 0))
                    with col_btn1: st.button("❤️ 已收藏" if is_bk else "🤍 收藏", key=f"bk_{row['Link']}", on_click=core_utils.toggle_bookmark_db, args=(row['Link'], is_bk))
                    with col_btn2:
                        with st.popover("🗑️"):
                            st.button("確定刪除", key=f"del_{row['Link']}", on_click=core_utils.delete_article_db, args=(row['Link'],), type="primary", use_container_width=True)
                
                if row['Image'] and str(row['Image']).startswith('http'):
                    img_html = f'<img src="{row["Image"]}" style="width:100%; max-width:800px; border-radius:8px; display:block; margin-bottom:15px; object-fit: cover;" loading="lazy">'
                    st.markdown(img_html, unsafe_allow_html=True)
                st.write(row['Summary'])
                st.markdown("---")

            if total_pages > 1:
                st.write("")
                col_space, col_page, col_space2 = st.columns([1, 2, 1])
                with col_page:
                    st.selectbox("📄 選擇頁數 (跳轉至)：", range(1, total_pages + 1), index=st.session_state.mono_page - 1, key="mono_page_selector", on_change=update_mono_page)
