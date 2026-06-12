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

    col_h1, col_h2 = st.columns([7, 3])
    with col_h1: st.header("🎓 Biblioapp：學術文獻與出版追蹤")
    with col_h2:
        st.write("")
        is_edit_mode = st.toggle("🛠️ 進入試算表管理模式", key="biblio_edit_mode")
    
    with st.sidebar:
        st.subheader("🔍 當前分頁搜尋")
        bib_local_search = st.text_input("輸入關鍵字", placeholder="在此分頁中過濾...", label_visibility="collapsed", on_change=reset_biblio_page)
        st.markdown("---")
        
        # 🌟 UI 優化：將待讀、已讀、實體合併為單一母選項「🔖 個人書庫」
        biblio_view_mode = st.radio("功能模式", ["📖 文獻探索", "🔖 個人書庫", "📚 參考書目", "🔗 網址備存", "🌐 可用資源", "🔍 搜尋中心"], on_change=reset_biblio_page)
        st.markdown("---")

        active_filter = "總覽 (依日期遞減)"
        db_type = "Book"
        active_shelf = "🔖 待讀書架" # 預設的子目錄書架

        if biblio_view_mode == "📖 文獻探索":
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
                    temp_df = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type=db_type, source_filter=active_filter, search_query=bib_local_search)
                    raw_issues = temp_df['issue_volume'].dropna().unique().tolist() if not temp_df.empty else []
                    clean_issues = [iss for iss in raw_issues if str(iss).strip()]
                    if clean_issues:
                        selected_issue = st.radio(f"{active_filter} 期號/版本：", clean_issues, on_change=reset_biblio_page)
                    else: selected_issue = None
                else: active_filter = selected_main
                
        # 🌟 UI 優化：當選擇「個人書庫」時，動態渲染次目錄單選按鈕
        elif biblio_view_mode == "🔖 個人書庫":
            st.subheader("📚 書架狀態")
            active_shelf = st.radio("選擇庫存狀態", ["🔖 待讀書架", "✅ 已讀書籍", "📦 實體書庫"], label_visibility="collapsed", on_change=reset_biblio_page)

    # ==========================================
    # 🌟 獨立的搜尋中心分頁
    # ==========================================
    if biblio_view_mode == "🔍 搜尋中心":
        st.subheader("🔍 全域搜尋中心")
        st.caption("在此輸入關鍵字，系統將自動跨越文獻、書架、參考書目與資源庫進行地毯式搜索。")
        global_q = st.text_input("跨板塊搜尋：", placeholder="搜尋書名、作者、筆記...", key="bib_global")
        st.markdown("---")

        if not global_q:
            st.info("👈 請在上方輸入關鍵字開始檢索。")
        else:
            df_pubs = core_utils.fetch_academic_pubs(view_mode="🔍 搜尋中心", search_query=global_q)
            if not df_pubs.empty:
                st.markdown(f"#### 📖 學術文獻與書架 ({len(df_pubs)} 筆)")
                status_dict = {1: "待讀書架", 2: "已讀書籍", 3: "實體書庫"}
                for _, row in df_pubs.iterrows():
                    location = "網址備存" if row.get('type') == 'Web Link' else status_dict.get(row.get('book_status', 0), "文獻探索")
                    st.markdown(f"- **[{row.get('title', '未命名')}]({row.get('link', '#')})** ｜ 👤 {row.get('author', '未知')} ｜ 📍 位於：`{location}`")
                st.write("")
                
            df_refs = core_utils.fetch_bibliography_references(search_query=global_q)
            if not df_refs.empty:
                st.markdown(f"#### 📚 參考書目 ({len(df_refs)} 筆)")
                for _, row in df_refs.iterrows():
                    st.markdown(f"- **[{row.get('title', '未命名')}]({row.get('link', '#')})** ｜ 👤 {row.get('author', '未知')} ｜ 📍 位於：`參考書目`")
                st.write("")

            df_res_web = core_utils.fetch_custom_resources("biblioapp", search_query=global_q)
            df_res_lec = core_utils.fetch_custom_resources("biblioapp_lecture", search_query=global_q)
            df_res_conf = core_utils.fetch_custom_resources("biblioapp_conference", search_query=global_q)
            
            if not df_res_web.empty or not df_res_lec.empty or not df_res_conf.empty:
                st.markdown("#### 🌐 講座、會議與資源")
                if not df_res_web.empty:
                    for _, row in df_res_web.iterrows(): st.markdown(f"- **[{row.get('title', '未命名')}]({row.get('url', '#')})** ｜ 📍 位於：`可用資源 > 網路資源`")
                if not df_res_lec.empty:
                    for _, row in df_res_lec.iterrows(): st.markdown(f"- **[{row.get('title', '未命名')}]({row.get('url', '#')})** ｜ 📍 位於：`可用資源 > 講座記錄`")
                if not df_res_conf.empty:
                    for _, row in df_res_conf.iterrows(): st.markdown(f"- **[{row.get('title', '未命名')}]({row.get('url', '#')})** ｜ 📍 位於：`可用資源 > 學術會議`")
            
            if df_pubs.empty and df_refs.empty and df_res_web.empty and df_res_lec.empty and df_res_conf.empty:
                st.warning(f"在 Biblioapp 模組中，找不到包含「{global_q}」的資料。")

    elif biblio_view_mode == "📚 參考書目":
        with st.expander("➕ 新增參考文獻 (自動與手動)", expanded=False):
            tab_auto, tab_man = st.tabs(["API 自動擷取", "手動輸入"])
            with tab_auto:
                col1, col2 = st.columns([2, 1])
                with col1: ref_input = st.text_input("輸入 DOI 或 ISBN：", key="ref_input_field")
                with col2: ref_importance = st.selectbox("重要等級：", ["S", "A", "A-", "B", "B-", "C", "C-", "待讀"], key="ref_imp_sel")
                ref_notes = st.text_area("文獻備註 / 核心觀點摘要：", key="ref_notes_field")
                if st.button("擷取並加入參考庫", use_container_width=True, type="primary"):
                    if ref_input:
                        with st.spinner("正在擷取..."):
                            success, msg = core_utils.add_bibliography_reference(ref_input, ref_importance, ref_notes)
                            if success: st.cache_data.clear(); st.success(msg); st.rerun()
                            else: st.error(msg)
            with tab_man:
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    manual_title = st.text_input("書名 / 論文名 (必填)：", key="man_ref_title")
                    manual_author = st.text_input("作者 (必填)：", key="man_ref_author")
                with col_m2:
                    manual_year = st.text_input("出版年份：", key="man_ref_year", max_chars=4)
                    manual_type = st.radio("文獻類型：", ["專書 (Book)", "期刊/論文 (Journal)"], horizontal=True, key="man_ref_type")
                manual_id = st.text_input("唯一識別碼 (必填)：", key="man_ref_id")
                col_man_imp, col_man_note = st.columns([1, 2])
                with col_man_imp: manual_importance = st.selectbox("重要等級：", ["S", "A", "A-", "B", "B-", "C", "C-", "待讀"], key="man_ref_imp")
                with col_man_note: manual_notes = st.text_area("文獻備註：", key="man_ref_notes")
                if st.button("💾 手動寫入參考庫", use_container_width=True):
                    if manual_title and manual_author and manual_id:
                        success, msg = core_utils.add_manual_bibliography_reference(manual_id, manual_title, manual_author, manual_importance, manual_notes, manual_year, manual_type)
                        if success: st.cache_data.clear(); st.success(msg); st.rerun()
                        else: st.error(msg)
                    else: st.warning("請務必填寫必填資訊。")

        st.subheader("📚 參考書目與註釋管理")
        st.markdown("---")

        df_refs = core_utils.fetch_bibliography_references(search_query=bib_local_search)
        df_refs = ui_components.apply_smart_sort(df_refs, table_name="bibliography_notes", context_key="ref_tab")
        
        if is_edit_mode:
            if df_refs.empty: st.info("目前無資料可供編輯。")
            else: ui_components.render_batch_editor(df_refs, table_name="bibliography_notes", key_prefix="ref")
        else:
            if df_refs.empty: st.info("目前沒有符合條件的參考書目。")
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
                
    elif biblio_view_mode == "📖 文獻探索":
        st.subheader(f"🏛️ {active_filter} - 目錄")
        st.markdown("---")

        df_pubs = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type=db_type, source_filter=active_filter, search_query=bib_local_search)
        if db_type == "Journal" and active_filter != "總覽 (依日期遞減)" and 'selected_issue' in locals() and selected_issue:
            df_pubs = df_pubs[df_pubs['issue_volume'] == selected_issue]

        df_pubs = ui_components.apply_smart_sort(df_pubs, table_name="academic_pubs", context_key="explore_tab")
        
        if is_edit_mode:
            if df_pubs.empty: st.info("目前無資料可供編輯。")
            else: ui_components.render_batch_editor(df_pubs, table_name="academic_pubs", key_prefix="explore")
        else:
            if df_pubs.empty: st.info("目前資料庫中沒有符合條件的書目。")
            else:
                if db_type == "Journal" and active_filter == "總覽 (依日期遞減)":
                    df_sorted = df_pubs.sort_values(by=['publish_date', 'issue_volume'], ascending=[False, False], na_position='last')
                    latest_records = df_sorted.drop_duplicates(subset=['publisher_journal'], keep='first')
                    latest_dfs = []
                    for _, row in latest_records.iterrows():
                        journal, issue, pub_date = row['publisher_journal'], row.get('issue_volume'), row.get('publish_date')
                        df_j = df_pubs[df_pubs['publisher_journal'] == journal]
                        if pd.notna(issue) and str(issue).strip() != "": latest_dfs.append(df_j[df_j['issue_volume'] == issue])
                        else: latest_dfs.append(df_j[df_j['publish_date'] == pub_date])
                    df_aggregated = pd.concat(latest_dfs) if latest_dfs else pd.DataFrame()
                    page_data, total_pages, current_page = ui_components.paginate_data(df_aggregated, per_page=100, session_key="biblio_page")
                    
                    current_rendering_journal = ""
                    for _, row in page_data.iterrows():
                        journal_name = row.get('publisher_journal', '未知期刊')
                        if journal_name != current_rendering_journal:
                            if current_rendering_journal != "": st.divider()
                            current_rendering_journal = journal_name
                            issue_display = row.get('issue_volume', row.get('publish_date', ''))
                            st.markdown(f"### 📖 {journal_name} (Latest | {issue_display})")
                            
                        col_text, col_btn = st.columns([15, 1])
                        with col_text:
                            doi_text, display_time = row.get('identifier', '無識別碼'), row.get('issue_volume', '') if pd.notna(row.get('issue_volume', '')) and row.get('issue_volume', '') else row.get('publish_date', '未知日期')
                            st.markdown(f"- **[{row.get('title', '未命名論文')}]({row.get('link', '#')})** ｜ 👤 *{row.get('author', '未知')}* ｜ 🔖 `{doi_text}` ｜ 📅 {display_time}")
                        with col_btn:
                            is_bk = row.get('book_status', 0) == 1
                            st.button("❤️" if is_bk else "🤍", key=f"bk_mini_{row['id']}", on_click=core_utils.update_book_status, args=([row['id']], 0 if is_bk else 1), help="加入/移除待讀")
                            
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
                                        st.markdown(f'''<img src="{img_url}" style="width:100%; max-width:140px; aspect-ratio:2/3; object-fit:contain; background-color:#1E1E1E; border-radius:4px; box-shadow: 0 4px 6px rgba(0,0,0,0.2);" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x225/2b2b2b/FFFFFF?text=No+Cover';">''', unsafe_allow_html=True)
                                    else: st.info("無封面圖影")
                                with col_info:
                                    st.markdown(f"### [{row.get('title', '未命名')}]({row.get('link', '#')})")
                                    st.caption(f"👤 **Author:** {row.get('author')} | 🏛️ **Publisher:** {row.get('publisher_journal')} | 📅 **Date:** {row.get('publish_date')}")
                                    st.write(row.get('abstract', ''))
                                with col_btn: ui_components.render_smart_popover(row, table_name="academic_pubs")
                            else:
                                col_info, col_btn = st.columns([8, 1])
                                with col_info:
                                    st.markdown(f"### [{row.get('title', '未命名論文')}]({row.get('link', '#')})")
                                    issue_text = f" | 🏷️ **Issue:** {row.get('issue_volume')}" if row.get('issue_volume') else ""
                                    st.caption(f"👤 **Author:** {row.get('author')} | 📄 **Journal:** {row.get('publisher_journal')}{issue_text} | 📅 **Date:** {row.get('publish_date')}")
                                    st.write(row.get('abstract', ''))
                                with col_btn: ui_components.render_smart_popover(row, table_name="academic_pubs")
                        st.divider()
                    ui_components.render_pagination_ui(total_pages, current_page, "biblio_page")

    # 🌟 UI 優化：將三種書架狀態合併於同一邏輯區塊處理，並將 API 代入 active_shelf
    elif biblio_view_mode == "🔖 個人書庫":
        # 僅在待讀書架顯示手動加入區塊 (保持邏輯合理)
        if active_shelf == "🔖 待讀書架":
            with st.expander("📥 手動新增待讀書目", expanded=False):
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
                            else: st.error("❌ 找不到該 ISBN。")
                    else: st.warning("⚠️ 請輸入 ISBN。")
            st.markdown("---")

        # 這裡的傳入參數改為 active_shelf
        df_pubs = core_utils.fetch_academic_pubs(view_mode=active_shelf, pub_type="Book", source_filter="總覽", search_query=bib_local_search)
        if 'category' not in df_pubs.columns: df_pubs['category'] = "未分類"
        df_pubs['category'] = df_pubs['category'].fillna("未分類").replace("", "未分類").replace("學術專著", "研究")
        
        BOOK_CATEGORIES = ["總覽", "未分類", "研究", "學術", "小說", "詩", "次文化", "藝術", "音樂"]
        selected_category = st.radio("📚 分類篩選：", BOOK_CATEGORIES, horizontal=True)
        if selected_category != "總覽": df_pubs = df_pubs[df_pubs['category'] == selected_category]

        st.subheader(f"{active_shelf} ({selected_category})")
        st.markdown("---")

        ctx_map = {"🔖 待讀書架": "bookshelf", "✅ 已讀書籍": "read", "📦 實體書庫": "physical"}
        ctx = ctx_map[active_shelf]

        df_pubs = ui_components.apply_smart_sort(df_pubs, table_name="academic_pubs", context_key=f"{ctx}_tab")

        if is_edit_mode:
            if df_pubs.empty: st.info(f"「{selected_category}」分類目前沒有符合的書籍。")
            else: ui_components.render_batch_editor(df_pubs, table_name="academic_pubs", key_prefix=ctx)
        else:
            if df_pubs.empty: st.info(f"目前沒有相符書籍。")
            else:
                if f'bib_{ctx}_grid_page' not in st.session_state: st.session_state[f'bib_{ctx}_grid_page'] = 1
                df_grid_page, total_grid_pages, current_grid_page = ui_components.paginate_data(df_pubs, per_page=15, session_key=f"bib_{ctx}_grid_page")
                cols = st.columns(5)
                for idx, row in df_grid_page.reset_index(drop=True).iterrows():
                    with cols[idx % 5]:
                        ui_components.render_grid_card(row)
                        ui_components.render_smart_popover(row, table_name="academic_pubs", context=ctx)
                        st.write("") 
                ui_components.render_pagination_ui(total_grid_pages, current_grid_page, f"bib_{ctx}_grid_page")
                        
    elif biblio_view_mode == "🔗 網址備存":
        with st.expander("📥 網址備存匯入 (當 ISBN 掃描失敗時強制擷取)", expanded=False):
            backup_url_input = st.text_input("貼上出版社或 Amazon 網址：", key="backup_url_field")
            if st.button("網頁解析並加入備存", use_container_width=True):
                if backup_url_input:
                    with st.spinner("正在探測網頁元資料..."):
                        url_book_data = core_utils.fetch_book_by_url(backup_url_input)
                        if url_book_data:
                            success, msg = core_utils.add_url_backup(url_book_data)
                            if success: st.success(msg)
                            else: st.error(msg)
                        else: st.error("❌ 無法從該網址中萃取出有效的圖書元資料。")
                else: st.warning("⚠️ 請輸入有效的網址。")

        st.subheader(f"🔗 網址備存清單")
        st.markdown("---")
        
        df_pubs = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type="Web Link", source_filter="總覽", search_query=bib_local_search)
        df_pubs = ui_components.apply_smart_sort(df_pubs, table_name="academic_pubs", context_key="weblink_tab")
        
        if is_edit_mode:
            if df_pubs.empty: st.info("目前無資料可供編輯。")
            else: ui_components.render_batch_editor(df_pubs, table_name="academic_pubs", key_prefix="weblink")
        else:
            if df_pubs.empty: st.info("目前沒有相符的備存資料。")
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
        
        with tab_res:
            st.subheader("🌐 網路資源")
            with st.expander("➕ 新增資源", expanded=False):
                col1, col2 = st.columns([5, 1])
                with col1: new_bib_url = st.text_input("新增資料庫/網站", placeholder="請貼上連結...", label_visibility="collapsed", key="bib_res_input")
                with col2:
                    if st.button("➕ 擷取並加入", use_container_width=True, key="bib_res_btn"):
                        if new_bib_url:
                            success, msg = core_utils.add_custom_resource("biblioapp", new_bib_url)
                            if success: st.success(msg)
                            else: st.error(msg)
            st.markdown("---")

            df_res = core_utils.fetch_custom_resources("biblioapp", search_query=bib_local_search)
            df_res = ui_components.apply_smart_sort(df_res, table_name="custom_resources", context_key="web")
            
            if is_edit_mode:
                if df_res.empty: st.info("無資料可編輯。")
                else: ui_components.render_batch_editor(df_res, table_name="custom_resources", key_prefix="bib_res")
            else:
                if df_res.empty: st.info("目前沒有相符記錄。")
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

        with tab_lec:
            st.subheader("🎙️ 講座記錄")
            with st.expander("➕ 新增講座", expanded=False):
                event_title_lec = st.text_input("講座名稱 / 主題 (必填)：", key="evt_title_biblioapp_lecture")
                event_url_lec = st.text_input("相關連結 (報名網址/影片回放)：", key="evt_url_biblioapp_lecture")
                event_notes_lec = st.text_area("講者 / 筆記 / 核心觀點：", height=150, key="evt_notes_biblioapp_lecture")
                if st.button("💾 儲存講座記錄", use_container_width=True, type="primary", key="btn_save_lec"):
                    if event_title_lec:
                        success, msg = core_utils.add_manual_custom_resource("biblioapp_lecture", event_title_lec, event_url_lec, event_notes_lec)
                        if success: st.success(msg); st.rerun()
                        else: st.error(msg)
            st.markdown("---")

            df_lec = core_utils.fetch_custom_resources("biblioapp_lecture", search_query=bib_local_search)
            df_lec = ui_components.apply_smart_sort(df_lec, table_name="custom_resources", context_key="lec")
                
            if is_edit_mode:
                if df_lec.empty: st.info("無資料可供編輯。")
                else: ui_components.render_batch_editor(df_lec, table_name="custom_resources", key_prefix="bib_lec")
            else:
                if df_lec.empty: st.info("沒有相符的講座記錄。")
                else:
                    page_data, total_pages, current_page = ui_components.paginate_data(df_lec, per_page=15, session_key="bib_lec_page")
                    for _, row in page_data.iterrows():
                        with st.container():
                            col_info, col_btn = st.columns([8, 1])
                            with col_info:
                                st.markdown(f"### {row['title']}")
                                if pd.notna(row.get('url')) and str(row.get('url')).strip() != "": st.markdown(f"🔗 **[參考連結]({row['url']})**")
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
                    
        with tab_conf:
            st.subheader("🏛️ 學術會議")
            with st.expander("➕ 新增會議", expanded=False):
                event_title_conf = st.text_input("會議名稱 / 主題 (必填)：", key="evt_title_biblioapp_conference")
                event_url_conf = st.text_input("相關連結 (議程/官方網站)：", key="evt_url_biblioapp_conference")
                event_notes_conf = st.text_area("議程筆記 / 發表心得：", height=150, key="evt_notes_biblioapp_conference")
                if st.button("💾 儲存會議記錄", use_container_width=True, type="primary", key="btn_save_conf"):
                    if event_title_conf:
                        success, msg = core_utils.add_manual_custom_resource("biblioapp_conference", event_title_conf, event_url_conf, event_notes_conf)
                        if success: st.success(msg); st.rerun()
                        else: st.error(msg)
            st.markdown("---")

            df_conf = core_utils.fetch_custom_resources("biblioapp_conference", search_query=bib_local_search)
            df_conf = ui_components.apply_smart_sort(df_conf, table_name="custom_resources", context_key="conf")
                
            if is_edit_mode:
                if df_conf.empty: st.info("無資料可供編輯。")
                else: ui_components.render_batch_editor(df_conf, table_name="custom_resources", key_prefix="bib_conf")
            else:
                if df_conf.empty: st.info("沒有相符的會議記錄。")
                else:
                    page_data, total_pages, current_page = ui_components.paginate_data(df_conf, per_page=15, session_key="bib_conf_page")
                    for _, row in page_data.iterrows():
                        with st.container():
                            col_info, col_btn = st.columns([8, 1])
                            with col_info:
                                st.markdown(f"### {row['title']}")
                                if pd.notna(row.get('url')) and str(row.get('url')).strip() != "": st.markdown(f"🔗 **[參考連結]({row['url']})**")
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
