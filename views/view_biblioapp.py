import streamlit as st
import math
import pandas as pd
import core_utils
from datetime import datetime

# ==========================================
# 共用輔助函數 (Pagination & Reset)
# ==========================================
def reset_biblio_page(): 
    st.session_state.biblio_page = 1
    st.session_state.bib_grid_page = 1

def _handle_pagination(total_items, per_page, session_key):
    """處理分頁計算，回傳起始索引與總頁數"""
    total_pages = max(1, math.ceil(total_items / per_page))
    if st.session_state.get(session_key, 1) > total_pages: 
        st.session_state[session_key] = total_pages
    start_idx = (st.session_state[session_key] - 1) * per_page
    return start_idx, total_pages

def _render_pagination_ui(total_pages, session_key):
    """渲染底部的分頁選擇器"""
    if total_pages > 1:
        st.write("")
        col_space, col_page, col_space2 = st.columns([1, 2, 1])
        with col_page:
            def update_page():
                st.session_state[session_key] = st.session_state[f"{session_key}_selector"]
            st.selectbox("📄 選擇頁數：", range(1, total_pages + 1), 
                         index=st.session_state[session_key] - 1, 
                         key=f"{session_key}_selector", 
                         on_change=update_page)

# ==========================================
# 子視圖元件 (Components)
# ==========================================

def _render_reference_lib():
    """📚 參考書目與註釋管理視圖"""
    col_title, col_sort = st.columns([3, 1])
    with col_title:
        st.subheader("📚 參考書目與註釋管理")
        st.caption("輸入 DOI 或 ISBN 擷取文獻元資料，並標註重要等級與個人備註，作為論文寫作的專屬引註庫。")
    with col_sort:
        ref_sort_mode = st.selectbox("🔀 排序方式：", ["最新加入", "重要等級 (高至低)", "出版日期 (新到舊)"], key="ref_sort")
    st.markdown("---")

    with st.expander("➕ 新增參考文獻 (API 自動擷取 DOI / ISBN)", expanded=False):
        col1, col2 = st.columns([2, 1])
        with col1:
            ref_input = st.text_input("輸入 DOI (如 10.1215/...) 或 ISBN：", placeholder="自動擷取作者、期刊、期號...")
        with col2:
            ref_importance = st.selectbox("重要等級：", ["S", "A", "A-", "B", "B-", "C", "C-", "待讀"])
        ref_notes = st.text_area("文獻備註 / 核心觀點摘要：", placeholder="輸入這篇文獻與你研究計畫的關聯性...")
        
        if st.button("擷取並加入參考庫", use_container_width=True, type="primary"):
            if ref_input:
                with st.spinner("正在呼叫 API 擷取元資料..."):
                    success, msg = core_utils.add_bibliography_reference(ref_input, ref_importance, ref_notes)
                    if success: st.cache_data.clear(); st.success(msg); st.rerun()
                    else: st.error(msg)
            else: st.warning("⚠️ 請輸入 DOI 或 ISBN。")
            
    with st.expander("📝 手動新增參考文獻 (無 API 紀錄時使用)", expanded=False):
        st.caption("若無法透過 API 自動獲取，請直接填寫資訊。請注意，DOI 或 ISBN 為必填欄位。")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            manual_title = st.text_input("書名 / 論文名 (必填)：", key="man_ref_title")
            manual_author = st.text_input("作者 (必填)：", key="man_ref_author")
        with col_m2:
            manual_year = st.text_input("出版年份 (例如: 1998)：", key="man_ref_year", max_chars=4)
            manual_type = st.radio("文獻類型：", ["專書 (Book)", "期刊/論文 (Journal)"], horizontal=True, key="man_ref_type")
        manual_id = st.text_input("DOI 或 ISBN (必填，作為防重複唯一碼)：", key="man_ref_id")
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
            else: st.warning("⚠️ 拒絕寫入：請務必填寫「書名/論文名」、「作者」與「DOI/ISBNftp」。")
    
    st.markdown("---")
    df_refs = core_utils.fetch_bibliography_references()
    if df_refs.empty:
        st.info("目前沒有任何參考書目。請在上方輸入 DOI 或 ISBN 建立你的文獻庫。")
        return
        
    if ref_sort_mode == "最新加入": df_refs = df_refs.sort_values(by='added_date', ascending=False)
    elif ref_sort_mode == "重要等級 (高至低)":
        imp_map = {"S": 1, "A": 2, "A-": 3, "B": 4, "B-": 5, "C": 6, "C-": 7, "待讀": 8}
        df_refs['sort_val'] = df_refs['importance'].map(imp_map).fillna(9)
        df_refs = df_refs.sort_values(by=['sort_val', 'added_date'], ascending=[True, False])
    elif ref_sort_mode == "出版日期 (新到舊)": df_refs = df_refs.sort_values(by='publish_date', ascending=False)
    
    for _, row in df_refs.iterrows():
        with st.container():
            col_info, col_btn = st.columns([8, 1])
            with col_info:
                st.markdown(f"### [{row.get('title', '未命名')}]({row.get('link', '#')})")
                st.caption(f"👤 **{row.get('author', '未知')}** | 🏛️ {row.get('publisher_journal', '')} {row.get('issue_volume', '')} | 📅 {row.get('publish_date', '')} | 🏷️ `{row.get('identifier', '')}`")
                st.markdown(f"**等級：** {row.get('importance', '未標記')}")
                if row.get('notes'): st.info(row.get('notes'))
            with col_btn:
                with st.popover("⚙️ 管理"):
                    current_imp = row.get('importance')
                    valid_imps = ["S", "A", "A-", "B", "B-", "C", "C-", "待讀"]
                    imp_idx = valid_imps.index(current_imp) if current_imp in valid_imps else 7
                    new_imp = st.selectbox("修改等級：", valid_imps, index=imp_idx, key=f"imp_{row['id']}")
                    new_notes = st.text_area("修改備註：", value=row.get('notes', ''), key=f"note_{row['id']}")
                    st.button("💾 儲存", key=f"save_ref_{row['id']}", on_click=core_utils.update_bibliography_reference, args=(row['id'], new_imp, new_notes), use_container_width=True)
                    st.button("🗑️ 刪除", key=f"del_ref_{row['id']}", on_click=core_utils.delete_bibliography_reference, args=(row['id'],), type="primary", use_container_width=True)
        st.divider()

def _render_exploration(df_pubs, db_type, active_filter, selected_issue):
    """🔍 文獻探索視圖"""
    if db_type == "Journal" and active_filter != "總覽 (依日期遞減)" and selected_issue:
        df_pubs = df_pubs[df_pubs['issue_volume'] == selected_issue]

    st.subheader(f"🏛️ {active_filter} - 目錄 (共 {len(df_pubs)} 筆)")
    st.markdown("---")
    
    if df_pubs.empty: 
        st.info("目前資料庫中沒有符合條件的書目。")
        return

    if db_type == "Journal" and active_filter == "總覽 (依日期遞減)":
        df_sorted = df_pubs.sort_values(by=['publish_date', 'issue_volume'], ascending=[False, False], na_position='last')
        latest_records = df_sorted.drop_duplicates(subset=['publisher_journal'], keep='first')
        latest_dfs = []
        for _, row in latest_records.iterrows():
            journal, issue, pub_date = row['publisher_journal'], row.get('issue_volume'), row.get('publish_date')
            df_j = df_pubs[df_pubs['publisher_journal'] == journal]
            latest_dfs.append(df_j[df_j['issue_volume'] == issue] if pd.notna(issue) and str(issue).strip() else df_j[df_j['publish_date'] == pub_date])
        
        df_aggregated = pd.concat(latest_dfs) if latest_dfs else pd.DataFrame()
        start_idx, total_pages = _handle_pagination(len(df_aggregated), 100, "biblio_page")
        current_page_df = df_aggregated.iloc[start_idx:start_idx + 100]
        
        current_rendering_journal = ""
        for _, row in current_page_df.iterrows():
            journal_name = row.get('publisher_journal', '未知期刊')
            if journal_name != current_rendering_journal:
                if current_rendering_journal != "": st.divider()
                current_rendering_journal = journal_name
                st.markdown(f"### 📖 {journal_name} (Latest | {row.get('issue_volume', row.get('publish_date', ''))})")
                
            col_text, col_btn = st.columns([15, 1])
            with col_text:
                issue_text = row.get('issue_volume', '')
                display_time = issue_text if pd.notna(issue_text) and issue_text else row.get('publish_date', '未知日期')
                st.markdown(f"- **[{row.get('title', '未命名論文')}]({row.get('link', '#')})** ｜ 👤 *{row.get('author', '未知')}* ｜ 🔖 `{row.get('identifier', '無識別碼')}` ｜ 📅 {display_time}")
            with col_btn:
                is_bk = bool(row.get('is_bookmarked', 0))
                st.button("❤️" if is_bk else "🤍", key=f"bk_mini_{row['id']}", on_click=core_utils.toggle_biblio_bookmark_db, args=(row['id'], is_bk), help="加入待讀")
        
        _render_pagination_ui(total_pages, "biblio_page")
    else:
        start_idx, total_pages = _handle_pagination(len(df_pubs), 20, "biblio_page")
        for _, row in df_pubs.iloc[start_idx:start_idx + 20].iterrows():
            with st.container():
                is_bk = bool(row.get('is_bookmarked', 0))
                if db_type == "Book":
                    col_img, col_info, col_btn = st.columns([2, 6, 1])
                    with col_img:
                        img_url = row.get('image')
                        if pd.notna(img_url) and (str(img_url).startswith("http") or str(img_url).startswith("data:")):
                            st.markdown(f'''<img src="{img_url}" style="width:100%; max-width:140px; aspect-ratio:2/3; object-fit:contain; background-color:#1E1E1E; border-radius:4px; box-shadow: 0 4px 6px rgba(0,0,0,0.2);">''', unsafe_allow_html=True)
                        else: st.info("無封面圖影")
                    with col_info:
                        st.markdown(f"### [{row.get('title', '未命名')}]({row.get('link', '#')})")
                        st.caption(f"👤 **Author:** {row.get('author')} | 🏛️ **Publisher:** {row.get('publisher_journal')} | 📅 **Date:** {row.get('publish_date')}")
                        st.write(row.get('abstract', ''))
                else:
                    col_info, col_btn = st.columns([8, 1])
                    with col_info:
                        st.markdown(f"### [{row.get('title', '未命名論文')}]({row.get('link', '#')})")
                        issue_text = f" | 🏷️ **Issue:** {row.get('issue_volume')}" if row.get('issue_volume') else ""
                        st.caption(f"👤 **Author:** {row.get('author')} | 📄 **Journal:** {row.get('publisher_journal')}{issue_text} | 📅 **Date:** {row.get('publish_date')}")
                        st.write(row.get('abstract', ''))
                with col_btn:
                    st.button("❤️ 已收" if is_bk else "🤍 收藏", key=f"bk_bib_{row['id']}", on_click=core_utils.toggle_biblio_bookmark_db, args=(row['id'], is_bk), use_container_width=True)
                    with st.popover("🗑️"):
                        st.button("✅ 確定刪除", key=f"del_list_{row['id']}", on_click=core_utils.delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
            st.divider()
            
        _render_pagination_ui(total_pages, "biblio_page")

def _render_bookshelf(df_pubs):
    """🔖 待讀書架視圖"""
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

    if 'category' not in df_pubs.columns: df_pubs['category'] = "未分類"
    df_pubs['category'] = df_pubs['category'].fillna("未分類").replace("", "未分類").replace("學術專著", "研究")
    
    BOOK_CATEGORIES = ["總覽", "未分類", "研究", "學術", "小說", "詩", "次文化", "藝術", "音樂"]
    selected_category = st.radio("📚 分類篩選：", BOOK_CATEGORIES, horizontal=True)

    if selected_category != "總覽":
        df_pubs = df_pubs[df_pubs['category'] == selected_category]

    if df_pubs.empty:
        st.subheader(f"🔖 待讀書架 ({selected_category} - 共 0 本)")
        st.markdown("---")
        st.info(f"「{selected_category}」分類目前是空的。")
        return

    col_title, col_sort = st.columns([3, 1])
    with col_title: st.subheader(f"🔖 待讀書架 ({selected_category} - 共 {len(df_pubs)} 本)")
    with col_sort:
        bib_sort_mode = st.selectbox("🔀 書架排序方式：", ["預設 (依加入順序)", "英文首字母 (A-Z)", "日文五十音", "漢字筆劃/部首"], key="bib_bookshelf_sort")
    st.markdown("---")

    if bib_sort_mode == "英文首字母 (A-Z)": df_pubs = df_pubs.sort_values(by='title', key=lambda col: col.str.lower())
    elif bib_sort_mode in ["日文五十音", "漢字筆劃/部首"]: df_pubs = df_pubs.sort_values(by='title')

    start_idx, total_pages = _handle_pagination(len(df_pubs), 15, "bib_grid_page")
    df_grid_page = df_pubs.iloc[start_idx:start_idx + 15]

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
            with btn_col1: st.button("💔 移除", key=f"unmark_{row['id']}_{idx}", on_click=core_utils.toggle_biblio_bookmark_db, args=(row['id'], 1), use_container_width=True)
            with btn_col2:
                with st.popover("⚙️"):
                    current_cat = row.get('category', '未分類')
                    valid_cats = ["未分類", "研究", "學術", "小說", "詩", "次文化", "藝術", "音樂"]
                    cat_idx = valid_cats.index(current_cat) if current_cat in valid_cats else 0
                    new_cat = st.selectbox("修改分類：", valid_cats, index=cat_idx, key=f"cat_{row['id']}_{idx}")
                    if st.button("💾 儲存分類", key=f"save_cat_{row['id']}_{idx}", use_container_width=True):
                        core_utils.update_biblio_category(row['id'], new_cat)
                        st.rerun() 
                    st.divider()
                    st.button("✅ 確定刪除", key=f"del_grid_{row['id']}_{idx}", on_click=core_utils.delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
            st.write("") 

    _render_pagination_ui(total_pages, "bib_grid_page")

def _render_url_backup(search_query):
    """🔗 網址備存視圖 (已修正：完美對齊 academic_pubs 表與舊有資料)"""
    st.subheader("🔗 網址備存與快照庫")
    st.caption("將 Amazon、各大出版社新書介紹頁或臨時發現的學術網址備存於此。")
    st.markdown("---")
    
    with st.expander("📥 智慧備存網址 (自動解析 Meta 標籤)", expanded=False):
        bk_url = st.text_input("輸入網址 URL：", placeholder="https://...", key="add_url_link")
        
        if st.button("💾 檢索並備存網址", use_container_width=True, type="primary"):
            if bk_url:
                with st.spinner("正在呼叫爬蟲擷取網頁元資料..."):
                    url_data = core_utils.fetch_book_by_url(bk_url)
                    if url_data:
                        success, msg = core_utils.add_url_backup(url_data)
                        if success: st.success(msg); st.rerun()
                        else: st.error(msg)
                    else: st.error("❌ 無法解析該網址，請確認網址是否有效。")
            else:
                st.warning("⚠️ 請輸入來源網址。")
                
    st.markdown("---")
    
    # 🎯 修正點：改回使用 fetch_academic_pubs 撈取 type = 'Web Link' 的歷史資料
    df_urls = core_utils.fetch_academic_pubs(view_mode="🔗 網址備存", pub_type="Web Link", source_filter="總覽", search_query=search_query)
    
    if df_urls.empty:
        st.info("目前沒有任何網址備存紀錄。")
        return
        
    start_idx, total_pages = _handle_pagination(len(df_urls), 15, "biblio_page")
    for _, row in df_urls.iloc[start_idx:start_idx + 15].iterrows():
        with st.container():
            col_info, col_btn = st.columns([8, 1])
            with col_info:
                st.markdown(f"#### [{row.get('title', '無標題')}]({row.get('link', '#')})")
                st.caption(f"🔗 備存網址: {row.get('link')} | 📅 建立時間: {row.get('publish_date', '未知')}")
                if pd.notna(row.get('abstract')) and str(row.get('abstract')).strip():
                    st.info(row['abstract'])
            with col_btn:
                with st.popover("⚙️"):
                    # 使用 academic_pubs 專用的刪除函數
                    st.button("✅ 確定刪除", key=f"del_url_{row['id']}", on_click=core_utils.delete_biblio_db, args=(row['id'],), type="primary", use_container_width=True)
        st.divider()
        
    _render_pagination_ui(total_pages, "biblio_page")


def _render_available_resources(search_query):
    """🌐 可用資源視圖 (已修正：還原歷史 Module 標籤)"""
    st.subheader("🌐 學術活動與可用資源")
    st.caption("集中管理線上學術講座（Lectures）與大型國際學術會議（Conferences）的徵稿資訊、直播連結及個人精華大綱。")
    st.markdown("---")
    
    tab_lec, tab_conf = st.tabs(["🎓 學術講座 (Lectures)", "🏛️ 學術會議 (Conferences)"])
    
    # --- Tab 1: 講座管理 ---
    with tab_lec:
        with st.expander("➕ 新增線上學術講座", expanded=False):
            lec_title = st.text_input("講座主題/講者名稱：", key="add_lec_title")
            lec_url = st.text_input("直播連結 / 詳情網址：", key="add_lec_url")
            lec_comment = st.text_area("核心筆記 / 講座大綱與講者資訊：", key="add_lec_comment", height=120)
            if st.button("💾 儲存講座資訊", key="save_new_lec", use_container_width=True, type="primary"):
                if lec_title:
                    # 🎯 修正點：將標籤改回原先預設的 "Lecture"
                    success, msg = core_utils.add_manual_custom_resource("Lecture", lec_title, lec_url, lec_comment)
                    if success: st.success(msg); st.rerun()
                    else: st.error(msg)
                else: st.warning("⚠️ 講座主題為必填欄位。")
                
        st.markdown("---")
        # 🎯 修正點：使用 "Lecture" 標籤撈取舊資料
        df_lec = core_utils.fetch_custom_resources("Lecture", search_query)
        if df_lec.empty:
            st.info("目前沒有任何講座紀錄。")
        else:
            for _, row in df_lec.iterrows():
                with st.container():
                    col_info, col_btn = st.columns([8, 1])
                    with col_info:
                        st.markdown(f"### [{row['title']}]({row.get('url', '#')})")
                        st.caption(f"🔗 連結網址: {row.get('url', '#')} | 📅 建立日期: {row.get('added_date','')}")
                        notes_text = str(row.get('comment', '')).strip()
                        if pd.notna(row.get('comment')) and notes_text:
                            if len(notes_text) > 120:
                                st.info(f"{notes_text[:120]} ...") 
                                with st.expander("📖 展開完整大綱與詳情"):
                                    st.markdown(notes_text.replace('\n', '  \n'))
                            else:
                                st.info(notes_text)
                    with col_btn:
                        with st.popover("⚙️ 管理"):
                            edit_title = st.text_input("修改主題：", value=row['title'], key=f"edit_lec_t_{row['id']}")
                            current_notes = row.get('comment', '') if pd.notna(row.get('comment')) else ""
                            edit_notes = st.text_area("修改筆記：", value=current_notes, key=f"edit_lec_note_{row['id']}", height=150)
                            st.button("💾 儲存", key=f"save_lec_{row['id']}", on_click=core_utils.update_custom_resource, args=(row['id'], edit_title, edit_notes), use_container_width=True)
                            st.button("🗑️ 刪除", key=f"del_lec_{row['id']}", on_click=core_utils.delete_custom_resource, args=(row['id'],), type="primary", use_container_width=True)
                st.divider()

    # --- Tab 2: 會議管理 ---
    with tab_conf:
        with st.expander("➕ 新增國際學術會議 (CFP)", expanded=False):
            conf_title = st.text_input("會議名稱 / 研討會主題：", key="add_conf_title")
            conf_url = st.text_input("會議官網 / 投稿入口 URL：", key="add_conf_url")
            conf_comment = st.text_area("重要日程 (如 Deadline) / 徵稿大綱：", key="add_conf_comment", height=120)
            if st.button("💾 儲存會議資訊", key="save_new_conf", use_container_width=True, type="primary"):
                if conf_title:
                    # 🎯 修正點：將標籤改回原先預設的 "Conference"
                    success, msg = core_utils.add_manual_custom_resource("Conference", conf_title, conf_url, conf_comment)
                    if success: st.success(msg); st.rerun()
                    else: st.error(msg)
                else: st.warning("⚠️ 會議名稱為必填欄位。")
                
        st.markdown("---")
        # 🎯 修正點：使用 "Conference" 標籤撈取舊資料
        df_conf = core_utils.fetch_custom_resources("Conference", search_query)
        if df_conf.empty:
            st.info("目前沒有任何研討會或會議紀錄。")
        else:
            for _, row in df_conf.iterrows():
                with st.container():
                    col_info, col_btn = st.columns([8, 1])
                    with col_info:
                        st.markdown(f"### [{row['title']}]({row.get('url', '#')})")
                        st.caption(f"🔗 會議官網: {row.get('url', '#')} | 📅 建立日期: {row.get('added_date','')}")
                        notes_text = str(row.get('comment', '')).strip()
                        if pd.notna(row.get('comment')) and notes_text:
                            if len(notes_text) > 120:
                                st.info(f"{notes_text[:120]} ...") 
                                with st.expander("📖 展開完整日程與詳情"):
                                    st.markdown(notes_text.replace('\n', '  \n'))
                            else:
                                st.info(notes_text)
                    with col_btn:
                        with st.popover("⚙️ 管理"):
                            edit_title = st.text_input("修改名稱：", value=row['title'], key=f"edit_conf_t_{row['id']}")
                            current_notes = row.get('comment', '') if pd.notna(row.get('comment')) else ""
                            edit_notes = st.text_area("修改日程/筆記：", value=current_notes, key=f"edit_conf_note_{row['id']}", height=150)
                            st.button("💾 儲存", key=f"save_conf_{row['id']}", on_click=core_utils.update_custom_resource, args=(row['id'], edit_title, edit_notes), use_container_width=True)
                            st.button("🗑️ 刪除", key=f"del_conf_{row['id']}", on_click=core_utils.delete_custom_resource, args=(row['id'],), type="primary", use_container_width=True)
                st.divider()
# ==========================================
# 主路由 (Router Entrance)
# ==========================================
def render_page():
    if 'biblio_page' not in st.session_state: st.session_state.biblio_page = 1
    if 'bib_grid_page' not in st.session_state: st.session_state.bib_grid_page = 1

    st.header("🎓 Biblioapp：學術文獻與出版追蹤")
    
    with st.sidebar:
        biblio_view_mode = st.radio("功能模式", ["🔍 文獻探索", "🔖 待讀書架", "📚 參考書目", "🔗 網址備存", "🌐 可用資源"], on_change=reset_biblio_page)
        st.markdown("---")
        st.subheader("🔍 全域搜尋")
        bib_search_query = st.text_input("輸入關鍵字", placeholder="書名、作者、出版社或摘要...", label_visibility="collapsed", on_change=reset_biblio_page)
        st.markdown("---")

        active_filter = "總覽 (依日期遞減)"
        db_type = "Book"
        selected_issue = None
        
        if biblio_view_mode == "🔍 文獻探索":
            st.subheader("文獻篩選")
            biblio_type_label = st.radio("文獻類型", ["📚 出版專書", "📄 期刊論文"], label_visibility="collapsed", on_change=reset_biblio_page)
            db_type = "Book" if "專書" in biblio_type_label else "Journal"
            
            if db_type == "Book":
                active_filter = st.selectbox("選擇出版社：", ["總覽 (依日期遞減)", "手動加入", "MIT Press", "Duke University Press", "青土社", "Urbanomic", "東京大学出版会", "Verso Books"], on_change=reset_biblio_page)
            else:
                st.subheader("選擇訂閱來源")
                journal_options = [
                    "總覽 (依日期遞減)", "📁 現代思想", "📁 ユリイカ", "📁 PRISM: Theory and Modern Chinese Literature",
                    "📁 Environmental Humanities", "📁 positions: asia critique", "📁 Science Fiction Studies",
                    "📁 boundary 2", "📁 MCLC", "📁 ISLE", "📁 Journal of World Literature (JWL)", "📁 Comparative Literature Studies (CLS)", "📁 Chinese literature and thought today"
                ]
                selected_main = st.selectbox("請選擇板塊：", journal_options, on_change=reset_biblio_page)
                if selected_main.startswith("📁 "):
                    active_filter = selected_main.replace("📁 ", "")
                    temp_df = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type=db_type, source_filter=active_filter, search_query=bib_search_query)
                    clean_issues = [iss for iss in temp_df['issue_volume'].dropna().unique().tolist() if str(iss).strip()]
                    if clean_issues: selected_issue = st.radio(f"{active_filter} 期號/版本：", clean_issues, on_change=reset_biblio_page)
                else:
                    active_filter = selected_main

    # 路由精準分發 (無任何省略)
    if biblio_view_mode == "📚 參考書目":
        _render_reference_lib()
    elif biblio_view_mode == "🔍 文獻探索":
        df_pubs = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type=db_type, source_filter=active_filter, search_query=bib_search_query)
        _render_exploration(df_pubs, db_type, active_filter, selected_issue)
    elif biblio_view_mode == "🔖 待讀書架":
        df_pubs = core_utils.fetch_academic_pubs(view_mode=biblio_view_mode, pub_type="Book", source_filter="總覽", search_query=bib_search_query)
        _render_bookshelf(df_pubs)
    elif biblio_view_mode == "🔗 網址備存":
        _render_url_backup(bib_search_query)
    elif biblio_view_mode == "🌐 可用資源":
        _render_available_resources(bib_search_query)
