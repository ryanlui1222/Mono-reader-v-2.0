import streamlit as st
import math
import pandas as pd
import core_utils
from datetime import datetime

def reset_biblio_page(): st.session_state.biblio_page = 1
def update_biblio_page(): 
    if "biblio_page_selector" in st.session_state: st.session_state.biblio_page = st.session_state.biblio_page_selector

def render_page():
    if 'biblio_page' not in st.session_state: st.session_state.biblio_page = 1
    if 'bib_grid_page' not in st.session_state: st.session_state.bib_grid_page = 1

    st.header("🎓 Biblioapp：學術文獻與出版追蹤")
    
    with st.sidebar:
        # 🌟 新增 📚 參考書目 節點
        biblio_view_mode = st.radio("功能模式", ["🔍 文獻探索", "🔖 待讀書架", "📚 參考書目", "🔗 網址備存", "🌐 可用資源"], on_change=reset_biblio_page)
        st.markdown("---")
        
        st.subheader("🔍 全域搜尋")
        bib_search_query = st.text_input("輸入關鍵字", placeholder="書名、作者、出版社或摘要...", label_visibility="collapsed", on_change=reset_biblio_page)
        st.markdown("---")
        
        with st.expander("📥 手動新增待讀書目 (ISBN)", expanded=False):
            isbn_input = st.text_input("輸入 ISBN：", placeholder="例如: 9780226321486")
            if st.button("檢索並加入書架", use_container_width=True):
                if isbn_input:
                    with st.spinner("正在呼叫多語系智能引擎..."):
                        book_data = core_utils.fetch_book_by_isbn(isbn_input)
                        if book_data:
                            book_data['publisher_journal'] = "手動加入"
                            try:
                                sql = "INSERT INTO academic_pubs (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image, is_bookmarked, is_manual) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1) ON CONFLICT(identifier) DO UPDATE SET title=excluded.title, image=excluded.image;"
                                core_utils.db.execute(sql, [book_data['type'], book_data['title'], book_data['author'], book_data['publisher_journal'], book_data['issue_volume'], book_data['identifier'], book_data['publish_date'], book_data['abstract'], book_data['link'], book_data['image']])
                                st.cache_data.clear(); st.success(f"✅ 已將《{book_data['title']}》加入清單！")
                            except Exception as e: st.error(f"寫入失敗: {e}")
                        else: st.error("❌ 找不到該 ISBN。請嘗試下方的網址備存功能。")
                else: st.warning("⚠️ 請輸入 ISBN。")
        
        with st.expander("📥 網址備存匯入 (當 ISBN 失敗時)", expanded=False):
            backup_url_input = st.text_input("貼上出版社或 Amazon 網址：", placeholder="https://...", key="backup_url_field")
            if st.button("網頁解析並加入備存", use_container_width=True, key="backup_url_btn"):
                if backup_url_input:
                    with st.spinner("正在探測網頁元資料..."):
                        url_book_data = core_utils.fetch_book_by_url(backup_url_input)
                        if url_book_data:
                            try:
                                sql = """
                                INSERT INTO academic_pubs (type, title, author, publisher_journal, issue_volume, identifier, publish_date, abstract, link, image, is_bookmarked, is_manual) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1) 
                                ON CONFLICT(identifier) DO UPDATE SET title=excluded.title;
                                """
                                core_utils.db.execute(sql, [
                                    url_book_data['type'], url_book_data['title'], url_book_data['author'], 
                                    url_book_data['publisher_journal'], url_book_data['issue_volume'], 
                                    url_book_data['identifier'], url_book_data['publish_date'], 
                                    url_book_data['abstract'], url_book_data['link'], url_book_data['image']
                                ])
                                st.cache_data.clear()
                                st.success(f"📋 備存成功！已將《{url_book_data['title']}》強行歸檔至「網址備存」清單！")
                            except Exception as e: 
                                st.error(f"寫入資料庫失敗: {e}")
                        else:
                            st.error("❌ 無法從該網址中萃取出有效的圖書元資料。")
                else:
                    st.warning("⚠️ 請輸入有效的網址。")
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
                    "總覽 (依日期遞減)", 
                    "📁 現代思想", 
                    "📁 ユリイカ", 
                    "📁 PRISM: Theory and Modern Chinese Literature",
                    "📁 Environmental Humanities",
                    "📁 positions: asia critique",
                    "📁 Science Fiction Studies"
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

    # 🌟 模組渲染區段
    if biblio_view_mode == "📚 參考書目":
        col_title, col_sort = st.columns([3, 1])
        with col_title:
            st.subheader("📚 參考書目與註釋管理")
            st.caption("輸入 DOI 或 ISBN 擷取文獻元資料，並標註重要等級與個人備註，作為論文寫作的專屬引註庫。")
        with col_sort:
            ref_sort_mode = st.selectbox(
                "🔀 排序方式：", 
                ["最新加入", "重要等級 (高至低)", "出版日期 (新到舊)"],
                key="ref_sort"
            )
        st.markdown("---")

        with st.expander("➕ 新增參考文獻", expanded=False):
            col1, col2 = st.columns([2, 1])
            with col1:
                ref_input = st.text_input("輸入 DOI (如 10.1215/...) 或 ISBN：", placeholder="自動擷取作者、期刊、期號...", key="ref_input_field")
            with col2:
                ref_importance = st.selectbox("重要等級：", ["🌟 核心文獻", "⭐ 重要參考", "📝 一般背景", "❓ 待評估"], key="ref_imp_sel")
            
            ref_notes = st.text_area("文獻備註 / 核心觀點摘要：", placeholder="輸入這篇文獻與你研究計畫的關聯性...", key="ref_notes_field")
            
            if st.button("擷取並加入參考庫", use_container_width=True, type="primary"):
                if ref_input:
                    with st.spinner("正在呼叫 API 擷取元資料..."):
                        success, msg = core_utils.add_bibliography_reference(ref_input, ref_importance, ref_notes)
                        if success:
                            st.cache_data.clear()
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.warning("⚠️ 請輸入 DOI 或 ISBN。")
        
        st.markdown("---")
        df_refs = core_utils.fetch_bibliography_references()
        
        if df_refs.empty:
            st.info("目前沒有任何參考書目。請在上方輸入 DOI 或 ISBN 建立你的文獻庫。")
        else:
            if ref_sort_mode == "最新加入":
                df_refs = df_refs.sort_values(by='added_date', ascending=False)
            elif ref_sort_mode == "重要等級 (高至低)":
                imp_map = {"🌟 核心文獻": 1, "⭐ 重要參考": 2, "📝 一般背景": 3, "❓ 待評估": 4}
                df_refs['sort_val'] = df_refs['importance'].map(imp_map).fillna(5)
                df_refs = df_refs.sort_values(by=['sort_val', 'added_date'], ascending=[True, False])
            elif ref_sort_mode == "出版日期 (新到舊)":
                df_refs = df_refs.sort_values(by='publish_date', ascending=False)
            
            for _, row in df_refs.iterrows():
                with st.container():
                    col_info, col_btn = st.columns([8, 1])
                    with col_info:
                        st.markdown(f"### [{row.get('title', '未命名')}]({row.get('link', '#')})")
                        meta_info = f"👤 **{row.get('author', '未知')}** | 🏛️ {row.get('publisher_journal', '')} {row.get('issue_volume', '')} | 📅 {row.get('publish_date', '')} | 🏷️ `{row.get('identifier', '')}`"
                        st.caption(meta_info)
                        st.markdown(f"**等級：** {row.get('importance', '未標記')}")
                        if row.get('notes'):
                            st.info(row.get('notes'))
                    with col_btn:
                        with st.popover("⚙️ 管理"):
                            current_imp = row.get('importance')
                            valid_imps = ["🌟 核心文獻", "⭐ 重要參考", "📝 一般背景", "❓ 待評估"]
                            imp_idx = valid_imps.index(current_imp) if current_imp in valid_imps else 3
                            
                            new_imp = st.selectbox("修改等級：", valid_imps, index=imp_idx, key=f"imp_{row['id']}")
                            new_notes = st.text_area("修改備註：", value=row.get('notes', ''), key=f"note_{row['id']}")
                            
                            st.button("💾 儲存", key=f"save_ref_{row['id']}", on_click=core_utils.update_bibliography_reference, args=(row['id'], new_imp, new_notes), use_container_width=True)
                            st.button("🗑️ 刪除", key=f"del_ref_{row['id']}", on_click=core_utils.delete_bibliography_reference, args=(row['id'],), type="primary", use_container_width=True)
                st.divider()

    elif biblio_view_mode == "🔍 文獻探索":
        df_pubs = core_utils.fetch_academic_pubs(
            view_mode=biblio_view_mode, 
            pub_type=db_type, 
            source_filter=active_filter,
            search_query=bib_search_query
        )
        
        # 套用樹狀資料夾過濾
        if db_type == "Journal" and active_filter != "總覽 (依日期遞減)" and 'selected_issue' in locals() and selected_issue:
            df_pubs = df_pubs[df_pubs['issue_volume'] == selected_issue]

        st.subheader(f"🏛️ {active_filter} - 目錄 (共 {len(df_pubs)} 筆)")
        st.markdown("---")
        
        if df_pubs.empty:
            st.info("目前資料庫中沒有符合條件的書目。")
        else:
            if db_type == "Journal" and active_filter == "總覽 (依日期遞減)":
                journals = df_pubs['publisher_journal'].dropna().unique()
                
                latest_dfs = []
                for journal in journals:
                    df_journal = df_pubs[df_pubs['publisher_journal'] == journal]
                    if not df_journal.empty:
                        latest_row = df_journal.iloc[0]
                        latest_issue_vol = latest_row.get('issue_volume', '')
                        latest_pub_date = latest_row.get('publish_date', '')
                        
                        if pd.notna(latest_issue_vol) and str(latest_issue_vol).strip() != "":
                            latest_dfs.append(df_journal[df_journal['issue_volume'] == latest_issue_vol])
                        else:
                            latest_dfs.append(df_journal[df_journal['publish_date'] == latest_pub_date])
                
                if latest_dfs:
                    df_aggregated = pd.concat(latest_dfs)
                    
                    PER_PAGE = 100
                    total_pages = math.ceil(len(df_aggregated) / PER_PAGE)
                    if st.session_state.biblio_page > total_pages and total_pages > 0: st.session_state.biblio_page = total_pages
                    start_idx = (st.session_state.biblio_page - 1) * PER_PAGE
                    
                    current_page_df = df_aggregated.iloc[start_idx:start_idx + PER_PAGE]
                    current_rendering_journal = ""
                    
                    for _, row in current_page_df.iterrows():
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
                            pub_date = row.get('publish_date', '未知日期')
                            issue_text = row.get('issue_volume', '')
                            display_time = issue_text if pd.notna(issue_text) and issue_text else pub_date
                            st.markdown(f"- **[{row.get('title', '未命名論文')}]({row.get('link', '#')})** ｜ 👤 *{row.get('author', '未知')}* ｜ 🔖 `{doi_text}` ｜ 📅 {display_time}")
                        with col_btn:
                            is_bk = bool(row.get('is_bookmarked', 0))
                            st.button("❤️" if is_bk else "🤍", key=f"bk_mini_{row['id']}", on_click=core_utils.toggle_biblio_bookmark_db, args=(row['id'], is_bk), help="加入待讀")

                    if total_pages > 1:
                        st.write("")
                        col_space, col_page, col_space2 = st.columns([1, 2, 1])
                        with col_page:
                            st.selectbox("📄 選擇頁數：", range(1, total_pages + 1), index=st.session_state.biblio_page - 1, key="biblio_page_selector", on_change=update_biblio_page)
            
            else:
                PER_PAGE = 20
                total_pages = math.ceil(len(df_pubs) / PER_PAGE)
                if st.session_state.biblio_page > total_pages and total_pages > 0: st.session_state.biblio_page = total_pages
                start_idx = (st.session_state.biblio_page - 1) * PER_PAGE
                
                for _, row in df_pubs.iloc[start_idx:start_idx + PER_PAGE].iterrows():
                    with st.container():
                        is_bk = bool(row.get('is_bookmarked', 0))
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
                                st.button("❤️ 已收" if is_bk else "🤍 收藏", key=f"bk_bib_{row['id']}", on_click=core_utils.toggle_biblio_bookmark_db, args=(row['id'], is_bk), use_container_width=True)
                                with st.popover("🗑️ 刪除"):
                                    st.write("確定抹除此書？")
                                    st.button("✅ 確定", key=f"del_list_{row['id']}", on_click=core_utils.delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
                        else:
                            col_info, col_btn = st.columns([8, 1])
                            with col_info:
                                st.markdown(f"### [{row.get('title', '未命名論文')}]({row.get('link', '#')})")
                                issue_text = f" | 🏷️ **Issue:** {row.get('issue_volume')}" if row.get('issue_volume') else ""
                                st.caption(f"👤 **Author:** {row.get('author')} | 📄 **Journal:** {row.get('publisher_journal')}{issue_text} | 📅 **Date:** {row.get('publish_date')}")
                                st.write(row.get('abstract', ''))
                            with col_btn:
                                st.button("❤️ 已收" if is_bk else "🤍 收藏", key=f"bk_bib_{row['id']}", on_click=core_utils.toggle_biblio_bookmark_db, args=(row['id'], is_bk), use_container_width=True)
                                with st.popover("🗑️ 刪除"):
                                    st.write("確定抹除此論文？")
                                    st.button("✅ 確定", key=f"del_list_jour_{row['id']}", on_click=core_utils.delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
                        st.divider()

                if total_pages > 1:
                    col_space, col_page, col_space2 = st.columns([1, 2, 1])
                    with col_page:
                        st.selectbox("📄 選擇頁數：", range(1, total_pages + 1), index=st.session_state.biblio_page - 1, key="biblio_page_selector", on_change=update_biblio_page)

    elif biblio_view_mode == "🔖 待讀書架":
        df_pubs = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type="Book", source_filter="總覽", search_query=bib_search_query)
        if df_pubs.empty:
            st.subheader("🔖 待讀書架 (共 0 本)")
            st.markdown("---")
            st.info("您的待讀書架目前是空的。請在文獻探索中點擊收藏，或在左側透過 ISBN 手動加入。")
        else:
            col_title, col_sort = st.columns([3, 1])
            with col_title:
                st.subheader(f"🔖 待讀書架 (共 {len(df_pubs)} 本)")
            with col_sort:
                bib_sort_mode = st.selectbox(
                    "🔀 書架排序方式：", 
                    ["預設 (依加入順序)", "英文首字母 (A-Z)", "日文五十音", "漢字筆劃/部首"],
                    key="bib_bookshelf_sort"
                )
            st.markdown("---")

            if bib_sort_mode == "英文首字母 (A-Z)":
                df_pubs = df_pubs.sort_values(by='title', key=lambda col: col.str.lower())
            elif bib_sort_mode in ["日文五十音", "漢字筆劃/部首"]:
                df_pubs = df_pubs.sort_values(by='title')

            PER_PAGE_GRID = 15
            total_grid_pages = math.ceil(len(df_pubs) / PER_PAGE_GRID)
            if st.session_state.bib_grid_page > total_grid_pages: st.session_state.bib_grid_page = max(1, total_grid_pages)
                
            start_grid_idx = (st.session_state.bib_grid_page - 1) * PER_PAGE_GRID
            df_grid_page = df_pubs.iloc[start_grid_idx:start_grid_idx + PER_PAGE_GRID]

            cols = st.columns(5)
            for idx, row in df_grid_page.reset_index(drop=True).iterrows():
                with cols[idx % 5]:
                    img_url = row.get('image')
                    if not img_url or (not str(img_url).startswith("http") and not str(img_url).startswith("data:")):
                        img_url = "https://via.placeholder.com/150x225/2b2b2b/FFFFFF?text=No+Cover"
                        
                    st.markdown(f'''
                    <div class="memoof-book">
                        <a href="{row.get('link', '#')}" target="_blank" class="memoof-cover">
                            <img src="{img_url}" onerror="this.onerror=null; this.src='https://via.placeholder.com/150x225/2b2b2b/FFFFFF?text=No+Cover';">
                        </a>
                        <div class="memoof-meta">
                            <div class="memoof-title" title="{row.get('title', '未命名')}">{row.get('title', '未命名')}</div>
                            <div class="memoof-author" title="{row.get('author', '')}">{row.get('author', '')}</div>
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1: 
                        st.button("💔 移除", key=f"unmark_{row['id']}_{idx}", on_click=core_utils.toggle_biblio_bookmark_db, args=(row['id'], 1), use_container_width=True)
                    with btn_col2:
                        with st.popover("🗑️ 刪除"):
                            st.write("確定抹除此書？")
                            st.button("✅ 確定", key=f"del_grid_{row['id']}_{idx}", on_click=core_utils.delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
                    st.write("") 

            if total_grid_pages > 1:
                st.write("")
                col_space, col_page, col_space2 = st.columns([1, 2, 1])
                with col_page:
                    chosen_grid_page = st.selectbox("📄 跳轉書架頁數：", range(1, total_grid_pages + 1), index=st.session_state.bib_grid_page - 1, key="bib_grid_page_selector")
                    if chosen_grid_page != st.session_state.bib_grid_page:
                        st.session_state.bib_grid_page = chosen_grid_page
                        st.rerun()

    elif biblio_view_mode == "🔗 網址備存":
        df_pubs = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type="Web Link", source_filter="總覽", search_query=bib_search_query)
        col_title, col_sort = st.columns([3, 1])
        with col_title:
            st.subheader(f"🔗 網址備存清單 (共 {len(df_pubs)} 筆)")
            st.caption("這裡存放了當 ISBN 掃描失敗時，透過網址強制解剖擷取的備用書籍資料。")
        with col_sort:
            web_sort_mode = st.selectbox(
                "🔀 排序方式：", 
                ["加入日期 (新到舊)", "加入日期 (舊到新)", "標題 (A-Z / 五十音)"],
                key="web_link_sort",
                on_change=reset_biblio_page
            )
        st.markdown("---")
        
        if df_pubs.empty:
            st.info("目前沒有任何網址備存資料。請在左側側邊欄貼上網址匯入。")
        else:
            if web_sort_mode == "加入日期 (舊到新)":
                df_pubs = df_pubs.sort_values(by='publish_date', ascending=True)
            elif web_sort_mode == "標題 (A-Z / 五十音)":
                df_pubs = df_pubs.sort_values(by='title', key=lambda col: col.str.lower(), ascending=True)

            PER_PAGE = 20
            total_pages = math.ceil(len(df_pubs) / PER_PAGE)
            if st.session_state.biblio_page > total_pages and total_pages > 0: st.session_state.biblio_page = total_pages
            start_idx = (st.session_state.biblio_page - 1) * PER_PAGE
            
            for _, row in df_pubs.iloc[start_idx:start_idx + PER_PAGE].iterrows():
                with st.container():
                    col_info, col_btn = st.columns([8, 1])
                    with col_info:
                        st.markdown(f"### [{row.get('title', '未命名')}]({row.get('link', '#')})")
                        st.caption(f"👤 **Author:** {row.get('author')} | 🌐 **Source:** 網址備存 | 📅 **Date Added:** {row.get('publish_date')}")
                        st.write(row.get('abstract', ''))
                    with col_btn:
                        with st.popover("🗑️ 刪除"):
                            st.write("確定抹除此紀錄？")
                            st.button("✅ 確定", key=f"del_web_{row['id']}", on_click=core_utils.delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
                st.divider()

            if total_pages > 1:
                col_space, col_page, col_space2 = st.columns([1, 2, 1])
                with col_page:
                    st.selectbox("📄 選擇頁數：", range(1, total_pages + 1), index=st.session_state.biblio_page - 1, key="biblio_page_selector", on_change=update_biblio_page)

    elif biblio_view_mode == "🌐 可用資源":
        st.subheader("🌐 可用資源 (Academic Resources)")
        st.caption("收集常用的學術資料庫、檢索系統或出版社官方網站。")
        
        with st.container():
            col1, col2 = st.columns([5, 1])
            with col1:
                new_bib_url = st.text_input("新增資料庫/網站", placeholder="請貼上網站連結...", label_visibility="collapsed", key="bib_res_input")
            with col2:
                if st.button("➕ 擷取並加入", use_container_width=True, key="bib_res_btn"):
                    if new_bib_url:
                        with st.spinner("擷取標題中..."):
                            success, msg = core_utils.add_custom_resource("biblioapp", new_bib_url)
                            if success: st.success(msg)
                            else: st.error(msg)
        st.markdown("---")

        df_res = core_utils.fetch_custom_resources("biblioapp")
        if df_res.empty:
            st.info("目前沒有任何記錄。請在上方輸入網址。")
        else:
            for _, row in df_res.iterrows():
                col_link, col_action = st.columns([7, 1])
                with col_link:
                    st.markdown(f"### {row['title']}")
                    st.markdown(f"🔗 **[前往資料庫]({row['url']})**")
                    comment_text = row.get('comment', '')
                    if pd.notna(comment_text) and str(comment_text).strip() != "":
                        st.info(f"{comment_text}")
                        
                with col_action:
                    with st.popover("⚙️ 管理"):
                        edit_title = st.text_input("修改顯示名稱：", value=row['title'], key=f"edit_bib_{row['id']}")
                        current_comment = row.get('comment', '') if pd.notna(row.get('comment')) else ""
                        edit_comment = st.text_area("編輯網站功能/內容介紹：", value=current_comment, key=f"edit_bib_cmt_{row['id']}", height=100)
                        st.button("💾 儲存修改", key=f"save_bib_{row['id']}", on_click=core_utils.update_custom_resource, args=(row['id'], edit_title, edit_comment), use_container_width=True)
                        st.button("🗑️ 刪除網站", key=f"del_bib_{row['id']}", on_click=core_utils.delete_custom_resource, args=(row['id'],), type="primary", use_container_width=True)
                st.divider()
