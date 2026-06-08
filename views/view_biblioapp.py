import streamlit as st
import pandas as pd
import core_utils
from datetime import datetime
from views import ui_components 

def reset_biblio_page(): 
    st.session_state.biblio_page = 1
    st.session_state.bib_ref_page = 1
    st.session_state.bib_res_page = 1
    st.session_state.bib_lec_page = 1
    st.session_state.bib_conf_page = 1

def render_page():
    if 'biblio_page' not in st.session_state: st.session_state.biblio_page = 1
    if 'bib_grid_page' not in st.session_state: st.session_state.bib_grid_page = 1

    # 🌟 頁面頂部的全域編輯開關
    col_h1, col_h2 = st.columns([7, 3])
    with col_h1: st.header("🎓 Biblioapp：學術文獻與出版追蹤")
    with col_h2:
        st.write("")
        is_edit_mode = st.toggle("🛠️ 進入試算表管理模式", key="biblio_edit_mode")
    
    with st.sidebar:
        biblio_view_mode = st.radio("功能模式", ["🔍 文獻探索", "🔖 待讀書架", "📚 參考書目", "🔗 網址備存", "🌐 可用資源"], on_change=reset_biblio_page)
        st.markdown("---")
        st.subheader("🔍 全域搜尋")
        bib_search_query = st.text_input("輸入關鍵字", placeholder="書名、作者、出版社或摘要...", label_visibility="collapsed", on_change=reset_biblio_page)
        st.markdown("---")

        active_filter = "總覽 (依日期遞減)"
        db_type = "Book"
        if biblio_view_mode == "🔍 文獻探索":
            st.subheader("文獻篩選")
            biblio_type_label = st.radio("文獻類型", ["📚 出版專書", "📄 期刊論文"], label_visibility="collapsed", on_change=reset_biblio_page)
            db_type = "Book" if "專書" in biblio_type_label else "Journal"
            active_filter = "總覽 (依日期遞減)"
            
            if db_type == "Book":
                active_filter = st.selectbox("選擇出版社：", ["總覽 (依日期遞減)", "手動加入", "MIT Press", "Duke University Press", "青土社", "Urbanomic", "東京大学出版会", "Verso Books"], on_change=reset_biblio_page)
            else:
                st.subheader("選擇訂閱來源")
                journal_options = [
                    "總覽 (依日期遞減)", "📁 現代思想", "📁 ユリイカ", "📁 PRISM: Theory and Modern Chinese Literature",
                    "📁 Environmental Humanities", "📁 positions: asia critique", "📁 Science Fiction Studies",
                    "📁 boundary 2", "📁 MCLC (Modern Chinese Literature and Culture)", 
                    "📁 ISLE: Interdisciplinary Studies in Literature and Environment", 
                    "📁 Journal of World Literature (JWL)", "📁 Comparative Literature Studies (CLS)",
                    "📁 Chinese literature and thought today"
                ]
                selected_main = st.selectbox("請選擇板塊：", journal_options, on_change=reset_biblio_page)
                
                if selected_main.startswith("📁 "):
                    active_filter = selected_main.replace("📁 ", "")
                    temp_df = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type=db_type, source_filter=active_filter, search_query=bib_search_query)
                    raw_issues = temp_df['issue_volume'].dropna().unique().tolist() if not temp_df.empty else []
                    clean_issues = [iss for iss in raw_issues if str(iss).strip()]
                    if clean_issues:
                        selected_issue = st.radio(f"{active_filter} 期號/版本：", clean_issues, on_change=reset_biblio_page)
                    else:
                        selected_issue = None
                else:
                    active_filter = selected_main

    if biblio_view_mode == "📚 參考書目":
        # 🌟 移除舊版的 col_title, col_sort 手刻選單，改用乾淨的標題
        st.subheader("📚 參考書目與註釋管理")
        st.caption("輸入 DOI 或 ISBN 擷取文獻元資料，並標註重要等級與個人備註，作為論文寫作的專屬引註庫。")
        st.markdown("---")

        with st.expander("➕ 新增參考文獻 (API 自動擷取 DOI / ISBN)", expanded=False):
            col1, col2 = st.columns([2, 1])
            with col1:
                ref_input = st.text_input("輸入 DOI (如 10.1215/...) 或 ISBN：", placeholder="自動擷取作者、期刊、期號...", key="ref_input_field")
            with col2:
                ref_importance = st.selectbox("重要等級：", ["S", "A", "A-", "B", "B-", "C", "C-", "待讀"], key="ref_imp_sel")
            ref_notes = st.text_area("文獻備註 / 核心觀點摘要：", placeholder="輸入這篇文獻與你研究計畫的關聯性...", key="ref_notes_field")
            if st.button("擷取並加入參考庫", use_container_width=True, type="primary"):
                if ref_input:
                    with st.spinner("正在呼叫 API 擷取元資料..."):
                        success, msg = core_utils.add_bibliography_reference(ref_input, ref_importance, ref_notes)
                        if success: st.cache_data.clear(); st.success(msg); st.rerun()
                        else: st.error(msg)
                else: st.warning("⚠️ 請輸入 DOI 或 ISBN。")
                
        with st.expander("📝 手動新增參考文獻 (無 API 紀錄時使用)", expanded=False):
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                manual_title = st.text_input("書名 / 論文名 (必填)：", key="man_ref_title")
                manual_author = st.text_input("作者 (必填)：", key="man_ref_author")
            with col_m2:
                manual_year = st.text_input("出版年份 (例如: 1998)：", key="man_ref_year", max_chars=4)
                manual_type = st.radio("文獻類型：", ["專書 (Book)", "期刊/論文 (Journal)"], horizontal=True, key="man_ref_type")
            manual_id = st.text_input("DOI 或 ISBN (必填，作為資料庫防重複的唯一識別碼)：", key="man_ref_id")
            col_man_imp, col_man_note = st.columns([1, 2])
            with col_man_imp:
                manual_importance = st.selectbox("重要等級：", ["S", "A", "A-", "B", "B-", "C", "C-", "待讀"], key="man_ref_imp")
            with col_man_note:
                manual_notes = st.text_area("文獻備註 / 核心觀點摘要：", key="man_ref_notes")
                
            if st.button("💾 手動寫入參考庫", use_container_width=True):
                if manual_title and manual_author and manual_id:
                    with st.spinner("正在寫入資料庫..."):
                        success, msg = core_utils.add_manual_bibliography_reference(manual_id, manual_title, manual_author, manual_importance, manual_notes, manual_year, manual_type)
                        if success: st.cache_data.clear(); st.success(msg); st.rerun()
                        else: st.error(msg)
                else: st.warning("⚠️ 拒絕寫入：請務必填寫必填資訊。")
        
        st.markdown("---")
        df_refs = core_utils.fetch_bibliography_references()
        
        # 🌟 植入全域排序，並將舊代碼完全抹除
        df_refs = ui_components.apply_smart_sort(df_refs, table_name="bibliography_notes", context_key="ref_tab")
        
        # 🌟 視圖分流
        if is_edit_mode:
            if df_refs.empty: st.info("目前無資料可供編輯。")
            else: ui_components.render_batch_editor(df_refs, table_name="bibliography_notes", key_prefix="ref")
        else:
            if df_refs.empty: st.info("目前沒有任何參考書目。請在上方輸入 DOI 或 ISBN 建立你的文獻庫。")
            else:
                page_data, total_pages, current_page = ui_components.paginate_data(df_refs, per_page=15, session_key="bib_ref_page")
                
                for _, row in page_data.iterrows():
                    with st.container():
                        col_info, col_btn = st.columns([8, 1])
                        with col_info:
                            st.markdown(f"### [{row.get('title', '未命名')}]({row.get('link', '#')})")
                            meta_info = f"👤 **{row.get('author', '未知')}** | 🏛️ {row.get('publisher_journal', '')} {row.get('issue_volume', '')} | 📅 {row.get('publish_date', '')} | 🏷️ `{row.get('identifier', '')}`"
                            st.caption(meta_info)
                            st.markdown(f"**等級：** {row.get('importance', '未標記')}")
                            if row.get('notes'): st.info(row.get('notes'))
                        with col_btn:
                            ui_components.render_smart_popover(row, table_name="bibliography_notes")
                    st.divider()
                ui_components.render_pagination_ui(total_pages, current_page, "bib_ref_page")
                
    elif biblio_view_mode == "🔍 文獻探索":
        df_pubs = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type=db_type, source_filter=active_filter, search_query=bib_search_query)
        if db_type == "Journal" and active_filter != "總覽 (依日期遞減)" and 'selected_issue' in locals() and selected_issue:
            df_pubs = df_pubs[df_pubs['issue_volume'] == selected_issue]

        st.subheader(f"🏛️ {active_filter} - 目錄 (共 {len(df_pubs)} 筆)")
        st.markdown("---")
        
        # 🌟 植入全域排序
        df_pubs = ui_components.apply_smart_sort(df_pubs, table_name="academic_pubs", context_key="explore_tab")
        
        # 🌟 視圖分流
        if is_edit_mode:
            if df_pubs.empty: st.info("目前無資料可供編輯。")
            else: ui_components.render_batch_editor(df_pubs, table_name="academic_pubs", key_prefix="explore")
        else:
            if df_pubs.empty: st.info("目前資料庫中沒有符合條件的書目。")
            else:
                if db_type == "Journal" and active_filter == "總覽 (依日期遞減)":
                    # 期刊總覽模式特有邏輯：只顯示各期刊最新一期
                    df_sorted = df_pubs.sort_values(by=['publish_date', 'issue_volume'], ascending=[False, False], na_position='last')
                    latest_records = df_sorted.drop_duplicates(subset=['publisher_journal'], keep='first')
                    
                    latest_dfs = []
                    for _, row in latest_records.iterrows():
                        journal = row['publisher_journal']
                        issue = row.get('issue_volume')
                        pub_date = row.get('publish_date')
                        df_j = df_pubs[df_pubs['publisher_journal'] == journal]
                        if pd.notna(issue) and str(issue).strip() != "": latest_dfs.append(df_j[df_j['issue_volume'] == issue])
                        else: latest_dfs.append(df_j[df_j['publish_date'] == pub_date])
                    
                    df_aggregated = pd.concat(latest_dfs) if latest_dfs else pd.DataFrame()
                        
                    page_data, total_pages, current_page = ui_components.paginate_data(df_aggregated, per_page=100, session_key="biblio_page")
                    
                    current_rendering_journal = ""
                    for _, row in page_data.iterrows():
                        journal_name = row.get('publisher_journal', '未知期刊')
                        if journal_name != current_rendering_journal:
                            if current_rendering_journal != "":
                                st.write("")
                                st.divider()
                            current_rendering_journal = journal_name
                            issue_display = row.get('issue_volume', row.get('publish_date', ''))
                            st.markdown(f"### 📖 {journal_name} (Latest | {issue_display})")
                            
                        col_text, col_btn = st.columns([15, 1])
                        with col_text:
                            doi_text = row.get('identifier', '無識別碼')
                            display_time = row.get('issue_volume', '') if pd.notna(row.get('issue_volume', '')) and row.get('issue_volume', '') else row.get('publish_date', '未知日期')
                            st.markdown(f"- **[{row.get('title', '未命名論文')}]({row.get('link', '#')})** ｜ 👤 *{row.get('author', '未知')}* ｜ 🔖 `{doi_text}` ｜ 📅 {display_time}")
                        with col_btn:
                            is_bk = bool(row.get('is_bookmarked', 0))
                            st.button("❤️" if is_bk else "🤍", key=f"bk_mini_{row['id']}", on_click=core_utils.toggle_bookmark, args=("academic_pubs", [row['id']], 0 if is_bk else 1), help="加入待讀")
                            
                    ui_components.render_pagination_ui(total_pages, current_page, "biblio_page")
                
                else:
                    page_data, total_pages, current_page = ui_components.paginate_data(df_pubs, per_page=20, session_key="biblio_page")
                    
                    for _, row in page_data.iterrows():
                        with st.container():
                            if db_type == "Book":
                                col_img, col_info, col_btn = st.columns([2, 6, 1])
                                with col_img:
                                    img_url = row.get('image')
                                    if pd.notna(img_url) and (str(img_url).startswith("http") or str(img_url).startswith("data:")):
                                        img_html = f'''<img src="{img_url}" style="width:100%; max-width:140px; aspect-ratio:2/3; object-fit:contain; background-color:#1E1E1E; border-radius:4px; box-shadow: 0 4px 6px rgba(0,0,0,0.2);" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x225/2b2b2b/FFFFFF?text=No+Cover';">'''
                                        st.markdown(img_html, unsafe_allow_html=True)
                                    else: st.info("無封面圖影")
                                with col_info:
                                    st.markdown(f"### [{row.get('title', '未命名')}]({row.get('link', '#')})")
                                    st.caption(f"👤 **Author:** {row.get('author')} | 🏛️ **Publisher:** {row.get('publisher_journal')} | 📅 **Date:** {row.get('publish_date')}")
                                    st.write(row.get('abstract', ''))
                                with col_btn:
                                    ui_components.render_smart_popover(row, table_name="academic_pubs")
                            else:
                                col_info, col_btn = st.columns([8, 1])
                                with col_info:
                                    st.markdown(f"### [{row.get('title', '未命名論文')}]({row.get('link', '#')})")
                                    issue_text = f" | 🏷️ **Issue:** {row.get('issue_volume')}" if row.get('issue_volume') else ""
                                    st.caption(f"👤 **Author:** {row.get('author')} | 📄 **Journal:** {row.get('publisher_journal')}{issue_text} | 📅 **Date:** {row.get('publish_date')}")
                                    st.write(row.get('abstract', ''))
                                with col_btn:
                                    ui_components.render_smart_popover(row, table_name="academic_pubs")
                        st.divider()
                            
                    ui_components.render_pagination_ui(total_pages, current_page, "biblio_page")

    elif biblio_view_mode == "🔖 待讀書架":
        with st.expander("📥 手動新增待讀書目 (利用 ISBN 智慧解析)", expanded=False):
            isbn_input = st.text_input("輸入 ISBN：", placeholder="例如: 9780226321486")
            if st.button("檢索並加入書架", use_container_width=True):
                if isbn_input:
                    with st.spinner("正在呼叫多語系智能引擎..."):
                        book_data = core_utils.fetch_book_by_isbn(isbn_input)
                        if book_data:
                            book_data['publisher_journal'] = "手動加入"
                            success, msg = core_utils.add_manual_book(book_data)
                            if success: st.success(msg)
                            else: st.error(msg)
                        else: st.error("❌ 找不到該 ISBN。請嘗試「網址備存」。")
                else: st.warning("⚠️ 請輸入 ISBN。")
        st.markdown("---")

        df_pubs = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type="Book", source_filter="總覽", search_query=bib_search_query)
        if 'category' not in df_pubs.columns: df_pubs['category'] = "未分類"
        df_pubs['category'] = df_pubs['category'].fillna("未分類").replace("", "未分類").replace("學術專著", "研究")
        
        BOOK_CATEGORIES = ["總覽", "未分類", "研究", "學術", "小說", "詩", "次文化", "藝術", "音樂"]
        selected_category = st.radio("📚 分類篩選：", BOOK_CATEGORIES, horizontal=True)

        if selected_category != "總覽":
            df_pubs = df_pubs[df_pubs['category'] == selected_category]

        st.subheader(f"🔖 待讀書架 ({selected_category} - 共 {len(df_pubs)} 本)")
        st.markdown("---")

        # 🌟 植入排序引擎 (並移除了原本手刻的 dropdown)
        df_pubs = ui_components.apply_smart_sort(df_pubs, table_name="academic_pubs", context_key="bookshelf_tab")

        # 🌟 視圖分流
        if is_edit_mode:
            if df_pubs.empty: st.info(f"「{selected_category}」分類目前是空的。")
            else: ui_components.render_batch_editor(df_pubs, table_name="academic_pubs", key_prefix="bookshelf")
        else:
            if df_pubs.empty:
                st.info(f"「{selected_category}」分類目前是空的。")
            else:
                df_grid_page, total_grid_pages, current_grid_page = ui_components.paginate_data(df_pubs, per_page=15, session_key="bib_grid_page")

                cols = st.columns(5)
                for idx, row in df_grid_page.reset_index(drop=True).iterrows():
                    with cols[idx % 5]:
                        ui_components.render_grid_card(row)
                        ui_components.render_smart_popover(row, table_name="academic_pubs", context="bookshelf")
                        st.write("") 
                
                ui_components.render_pagination_ui(total_grid_pages, current_grid_page, "bib_grid_page")
                        
    elif biblio_view_mode == "🔗 網址備存":
        with st.expander("📥 網址備存匯入 (當 ISBN 掃描失敗時強制擷取)", expanded=False):
            backup_url_input = st.text_input("貼上出版社或 Amazon 網址：", placeholder="https://...", key="backup_url_field")
            if st.button("網頁解析並加入備存", use_container_width=True, key="backup_url_btn"):
                if backup_url_input:
                    with st.spinner("正在探測網頁元資料..."):
                        url_book_data = core_utils.fetch_book_by_url(backup_url_input)
                        if url_book_data:
                            success, msg = core_utils.add_url_backup(url_book_data)
                            if success: st.success(msg)
                            else: st.error(msg)
                        else: st.error("❌ 無法從該網址中萃取出有效的圖書元資料。")
                else: st.warning("⚠️ 請輸入有效的網址。")
        st.markdown("---")
        
        df_pubs = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type="Web Link", source_filter="總覽", search_query=bib_search_query)
        st.subheader(f"🔗 網址備存清單 (共 {len(df_pubs)} 筆)")
        st.caption("這裡存放了當 ISBN 掃描失敗時，透過網址強制解剖擷取的備用書籍資料。")
        st.markdown("---")
        
        # 🌟 植入排序引擎
        df_pubs = ui_components.apply_smart_sort(df_pubs, table_name="academic_pubs", context_key="weblink_tab")
        
        # 🌟 視圖分流
        if is_edit_mode:
            if df_pubs.empty: st.info("目前無資料可供編輯。")
            else: ui_components.render_batch_editor(df_pubs, table_name="academic_pubs", key_prefix="weblink")
        else:
            if df_pubs.empty: st.info("目前沒有任何網址備存資料。請在上方展開區塊貼上網址匯入。")
            else:
                page_data, total_pages, current_page = ui_components.paginate_data(df_pubs, per_page=20, session_key="biblio_page")
                
                for _, row in page_data.iterrows():
                    with st.container():
                        col_info, col_btn = st.columns([8, 1])
                        with col_info:
                            st.markdown(f"### [{row.get('title', '未命名')}]({row.get('link', '#')})")
                            st.caption(f"👤 **Author:** {row.get('author')} | 🌐 **Source:** 網址備存 | 📅 **Date Added:** {row.get('publish_date')}")
                            st.write(row.get('abstract', ''))
                        with col_btn:
                            ui_components.render_smart_popover(row, table_name="academic_pubs")
                    st.divider()

                ui_components.render_pagination_ui(total_pages, current_page, "biblio_page")

    elif biblio_view_mode == "🌐 可用資源":
        tab_res, tab_lec, tab_conf = st.tabs(["🌐 網路資源", "🎙️ 講座記錄", "🏛️ 學術會議"])
        
        # ==========================================
        # Tab 1: 網路資源
        # ==========================================
        with tab_res:
            st.subheader("🌐 網路資源")
            st.caption("收集常用的學術資料庫、檢索系統或出版社官方網站 (貼上網址自動擷取標題)。")
            with st.container():
                col1, col2 = st.columns([5, 1])
                with col1: new_bib_url = st.text_input("新增資料庫/網站", placeholder="請貼上網站連結...", label_visibility="collapsed", key="bib_res_input")
                with col2:
                    if st.button("➕ 擷取並加入", use_container_width=True, key="bib_res_btn"):
                        if new_bib_url:
                            with st.spinner("擷取標題中..."):
                                success, msg = core_utils.add_custom_resource("biblioapp", new_bib_url)
                                if success: st.success(msg)
                                else: st.error(msg)
            st.markdown("---")

            df_res = core_utils.fetch_custom_resources("biblioapp")
            # 🌟 植入排序引擎
            df_res = ui_components.apply_smart_sort(df_res, table_name="custom_resources", context_key="web")
            
            # 🌟 視圖分流
            if is_edit_mode:
                if df_res.empty: st.info("目前無資料可供編輯。")
                else: ui_components.render_batch_editor(df_res, table_name="custom_resources", key_prefix="bib_res")
            else:
                if df_res.empty: st.info("目前沒有任何記錄。請在上方輸入網址。")
                else:
                    page_data, total_pages, current_page = ui_components.paginate_data(df_res, per_page=15, session_key="bib_res_page")
                    for _, row in page_data.iterrows():
                        col_link, col_action = st.columns([7, 1])
                        with col_link:
                            st.markdown(f"### {row['title']}")
                            st.markdown(f"🔗 **[前往資料庫]({row['url']})**")
                            if pd.notna(row.get('comment')) and str(row.get('comment')).strip() != "": st.info(f"{row['comment']}")
                        with col_action:
                            ui_components.render_smart_popover(row, table_name="custom_resources")
                        st.divider()
                    ui_components.render_pagination_ui(total_pages, current_page, "bib_res_page")

        # ==========================================
        # Tab 2: 講座記錄 
        # ==========================================
        with tab_lec:
            st.subheader("🎙️ 講座記錄")
            st.caption("手動記錄重要的學術講座，方便日後檢索回顧。")
            with st.expander("➕ 新增講座", expanded=False):
                event_title_lec = st.text_input("講座名稱 / 主題 (必填)：", key="evt_title_biblioapp_lecture")
                event_url_lec = st.text_input("相關連結 (報名網址/影片回放)：", key="evt_url_biblioapp_lecture")
                event_notes_lec = st.text_area("講者 / 筆記 / 核心觀點：", height=150, key="evt_notes_biblioapp_lecture")
                if st.button("💾 儲存講座記錄", use_container_width=True, type="primary", key="btn_save_lec"):
                    if event_title_lec:
                        success, msg = core_utils.add_manual_custom_resource("biblioapp_lecture", event_title_lec, event_url_lec, event_notes_lec)
                        if success: st.success(msg); st.rerun()
                        else: st.error(msg)
                    else: st.warning("⚠️ 請務必填寫名稱。")
            st.markdown("---")

            df_lec = core_utils.fetch_custom_resources("biblioapp_lecture")
            if bib_search_query and not df_lec.empty:
                mask = df_lec['title'].str.contains(bib_search_query, case=False, na=False) | df_lec['comment'].str.contains(bib_search_query, case=False, na=False)
                df_lec = df_lec[mask]
                
            # 🌟 植入排序引擎
            df_lec = ui_components.apply_smart_sort(df_lec, table_name="custom_resources", context_key="lec")
                
            # 🌟 視圖分流
            if is_edit_mode:
                if df_lec.empty: st.info("目前無資料可供編輯。")
                else: ui_components.render_batch_editor(df_lec, table_name="custom_resources", key_prefix="bib_lec")
            else:
                if df_lec.empty: st.info("目前沒有符合條件的講座記錄。")
                else:
                    page_data, total_pages, current_page = ui_components.paginate_data(df_lec, per_page=15, session_key="bib_lec_page")
                    for _, row in page_data.iterrows():
                        with st.container():
                            col_info, col_btn = st.columns([8, 1])
                            with col_info:
                                st.markdown(f"### {row['title']}")
                                if pd.notna(row.get('url')) and str(row.get('url')).strip() != "":
                                    st.markdown(f"🔗 **[參考連結]({row['url']})**")
                                notes_text = str(row.get('comment', '')).strip()
                                if pd.notna(row.get('comment')) and notes_text:
                                    if len(notes_text) > 120:
                                        st.info(f"{notes_text[:120]} ...") 
                                        with st.expander("📖 展開完整大綱與詳情"): st.markdown(notes_text.replace('\n', '  \n'))
                                    else: st.info(notes_text)
                            with col_btn:
                                ui_components.render_smart_popover(row, table_name="custom_resources")
                        st.divider()
                    ui_components.render_pagination_ui(total_pages, current_page, "bib_lec_page")
                    
        # ==========================================
        # Tab 3: 學術會議
        # ==========================================
        with tab_conf:
            st.subheader("🏛️ 學術會議")
            st.caption("手動記錄參與過或即將舉辦的學術會議與研討會。")
            with st.expander("➕ 新增會議", expanded=False):
                event_title_conf = st.text_input("會議名稱 / 主題 (必填)：", key="evt_title_biblioapp_conference")
                event_url_conf = st.text_input("相關連結 (議程/官方網站)：", key="evt_url_biblioapp_conference")
                event_notes_conf = st.text_area("議程筆記 / 發表心得：", height=150, key="evt_notes_biblioapp_conference")
                if st.button("💾 儲存會議記錄", use_container_width=True, type="primary", key="btn_save_conf"):
                    if event_title_conf:
                        success, msg = core_utils.add_manual_custom_resource("biblioapp_conference", event_title_conf, event_url_conf, event_notes_conf)
                        if success: st.success(msg); st.rerun()
                        else: st.error(msg)
                    else: st.warning("⚠️ 請務必填寫名稱。")
            st.markdown("---")

            df_conf = core_utils.fetch_custom_resources("biblioapp_conference")
            if bib_search_query and not df_conf.empty:
                mask = df_conf['title'].str.contains(bib_search_query, case=False, na=False) | df_conf['comment'].str.contains(bib_search_query, case=False, na=False)
                df_conf = df_conf[mask]
                
            # 🌟 植入排序引擎
            df_conf = ui_components.apply_smart_sort(df_conf, table_name="custom_resources", context_key="conf")
                
            # 🌟 視圖分流
            if is_edit_mode:
                if df_conf.empty: st.info("目前無資料可供編輯。")
                else: ui_components.render_batch_editor(df_conf, table_name="custom_resources", key_prefix="bib_conf")
            else:
                if df_conf.empty: st.info("目前沒有符合條件的會議記錄。")
                else:
                    page_data, total_pages, current_page = ui_components.paginate_data(df_conf, per_page=15, session_key="bib_conf_page")
                    for _, row in page_data.iterrows():
                        with st.container():
                            col_info, col_btn = st.columns([8, 1])
                            with col_info:
                                st.markdown(f"### {row['title']}")
                                if pd.notna(row.get('url')) and str(row.get('url')).strip() != "":
                                    st.markdown(f"🔗 **[參考連結]({row['url']})**")
                                notes_text = str(row.get('comment', '')).strip()
                                if pd.notna(row.get('comment')) and notes_text:
                                    if len(notes_text) > 120:
                                        st.info(f"{notes_text[:120]} ...") 
                                        with st.expander("📖 展開完整日程與詳情"): st.markdown(notes_text.replace('\n', '  \n'))
                                    else: st.info(notes_text)
                            with col_btn:
                                ui_components.render_smart_popover(row, table_name="custom_resources")
                        st.divider()
                    ui_components.render_pagination_ui(total_pages, current_page, "bib_conf_page")
