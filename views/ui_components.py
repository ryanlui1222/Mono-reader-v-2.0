import streamlit as st
import math
import pandas as pd
import core_utils 

# ==========================================
# 1. 全域分頁引擎 (Universal Pagination) - 兩階段版
# ==========================================
def paginate_data(data, per_page, session_key):
    total_items = len(data)
    if total_items == 0: return data, 0, 1

    total_pages = max(1, math.ceil(total_items / per_page))
    if session_key not in st.session_state: st.session_state[session_key] = 1
    if st.session_state[session_key] > total_pages: st.session_state[session_key] = total_pages

    current_page = st.session_state[session_key]
    start_idx = (current_page - 1) * per_page
    end_idx = start_idx + per_page

    if isinstance(data, pd.DataFrame): page_data = data.iloc[start_idx:end_idx]
    else: page_data = data[start_idx:end_idx]

    return page_data, total_pages, current_page

def render_pagination_ui(total_pages, current_page, session_key):
    if total_pages <= 1: return
    st.write("") 
    st.markdown("---")
    col_prev, col_page, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if st.button("⬅️ 上一頁", disabled=(current_page <= 1), key=f"prev_{session_key}", use_container_width=True):
            st.session_state[session_key] -= 1
            st.rerun()
    with col_page:
        def update_page(): st.session_state[session_key] = st.session_state[f"{session_key}_selector"]
        st.selectbox("📄 選擇頁數：", range(1, total_pages + 1), index=current_page - 1, key=f"{session_key}_selector", on_change=update_page, label_visibility="collapsed")
    with col_next:
        if st.button("下一頁 ➡️", disabled=(current_page >= total_pages), key=f"next_{session_key}", use_container_width=True):
            st.session_state[session_key] += 1
            st.rerun()

# ==========================================
# 2. 全域網格卡片渲染 (Universal Grid Card)
# ==========================================
def render_grid_card(row):
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

# ==========================================
# 3. 智慧管理按鈕 (混合模式：Popover + Dialog)
# ==========================================
@st.dialog("⚙️ 項目管理與編輯 (進階)")
def _edit_dialog(row, table_name, context, item_id, current_title, current_summary, k_id):
    """【軌道 A】用於大量文字編輯的獨立大型視窗"""
    st.markdown(f"**(ID: `{str(item_id)[:20]}...`)**")
    
    if table_name == "custom_resources":
        edit_title = st.text_input("修改名稱:", value=current_title, key=f"d_t_{k_id}")
        edit_summary = st.text_area("說明文字:", value=current_summary, key=f"d_c_{k_id}", height=250)
        
        if st.button("💾 儲存修改", key=f"d_save_{k_id}", use_container_width=True, type="primary"):
            core_utils.update_custom_resource(item_id, edit_title, edit_summary)
            st.cache_data.clear() 
            st.rerun()

    elif table_name == "omni_vault":  # 🌟 萬物收藏匣專屬編輯邏輯
        edit_cat = st.text_input("分類標籤 (可自訂):", value=row.get('category', ''), key=f"d_cat_{k_id}")
        edit_title = st.text_input("修改名稱:", value=current_title, key=f"d_t_{k_id}")
        edit_summary = st.text_area("說明文字/筆記:", value=current_summary, key=f"d_c_{k_id}", height=200)
        
        if st.button("💾 儲存修改", key=f"d_save_{k_id}", use_container_width=True, type="primary"):
            core_utils.update_omni_item(item_id, edit_cat, edit_title, edit_summary)
            st.cache_data.clear()
            st.rerun()

    elif table_name == "bibliography_notes":
        edit_title = st.text_input("修改標題:", value=current_title, key=f"d_t_{k_id}")
        current_imp = row.get('importance', '待讀')
        valid_imps = ["S", "A", "A-", "B", "B-", "C", "C-", "待讀"]
        imp_idx = valid_imps.index(current_imp) if current_imp in valid_imps else 7
        edit_imp = st.selectbox("評級 (Importance):", valid_imps, index=imp_idx, key=f"d_imp_{k_id}")
        edit_notes = st.text_area("備註 (Notes):", value=row.get('notes', ''), key=f"d_n_{k_id}", height=300)
        
        if st.button("💾 儲存修改", key=f"d_save_{k_id}", use_container_width=True, type="primary"):
            core_utils.update_bibliography_reference(item_id, edit_imp, edit_notes)
            core_utils.db.execute("UPDATE bibliography_notes SET title = ? WHERE id = ?", [edit_title, item_id])
            st.cache_data.clear() 
            st.rerun()

    st.divider()
    st.markdown("<span style='color:#EF4444;'>**⚠️ 危險區域**</span>", unsafe_allow_html=True)
    confirm_del = st.checkbox("我確定要解鎖徹底刪除", key=f"d_conf_{k_id}")
    if st.button("💥 執行徹底刪除", key=f"d_del_{k_id}", type="primary", disabled=not confirm_del, use_container_width=True):
        if table_name == "custom_resources": core_utils.delete_custom_resource(item_id)
        elif table_name == "bibliography_notes": core_utils.delete_bibliography_reference(item_id)
        elif table_name == "omni_vault": core_utils.delete_omni_item(item_id) # 🌟 萬物收藏匣刪除邏輯
        st.cache_data.clear() 
        st.rerun()


def _edit_popover(row, table_name, context, item_id, current_title, current_summary, is_bk, k_id):
    """【軌道 B】用於快速編輯的輕量級氣泡視窗"""
    with st.popover("⚙️ 管理", use_container_width=True):
        st.markdown(f"**📝 編輯項目** (ID: `{str(item_id)[:15]}...`)")
        
        edit_title = st.text_input("手動改名:", value=current_title, key=f"p_t_{k_id}")
        
        if table_name in ["academic_pubs", "media_vault"]:
            edit_summary = st.text_area("修改摘要/簡介:", value=current_summary, key=f"p_c_{k_id}", height=100)
        else:
            edit_summary = current_summary
        
        if context == "bookshelf":
            current_cat = row.get('category', '未分類')
            valid_cats = ["未分類", "研究", "學術", "小說", "詩", "次文化", "藝術", "音樂"]
            cat_idx = valid_cats.index(current_cat) if current_cat in valid_cats else 0
            new_cat = st.selectbox("📚 變更書架分類：", valid_cats, index=cat_idx, key=f"p_cat_{k_id}")

        if st.button("💾 儲存文字變更", key=f"p_save_{k_id}", use_container_width=True, type="primary"):
            if table_name == "articles":
                core_utils.update_article_meta(item_id, edit_title)
            elif table_name == "academic_pubs":
                core_utils.update_academic_pub_meta(item_id, edit_title, edit_summary)
                if context == "bookshelf": core_utils.update_biblio_category(item_id, new_cat)
            elif table_name == "media_vault":
                core_utils.update_media_vault_meta(item_id, edit_title, edit_summary)
            st.cache_data.clear() 
            st.rerun()

        st.divider()
        st.markdown("**⭐ 狀態管理**")
        if table_name == "articles":
            if st.button("💔 移除收藏" if is_bk else "❤️ 加入收藏", key=f"p_toggle_bk_{k_id}", use_container_width=True):
                core_utils.toggle_bookmark_db(item_id, is_bk)
                st.cache_data.clear()
                st.rerun()
        elif table_name == "academic_pubs":
            btn_label = "💔 移出書架" if context == "bookshelf" else ("💔 取消收藏" if is_bk else "❤️ 收藏文獻")
            if st.button(btn_label, key=f"p_toggle_bk_{k_id}", use_container_width=True):
                core_utils.toggle_biblio_bookmark_db(item_id, is_bk)
                st.cache_data.clear()
                st.rerun()
        elif table_name == "media_vault":
            mv_label = "✅ 標記為已完食" if is_bk else "⏳ 退回待播清單"
            next_state = 0 if is_bk else 1
            if st.button(mv_label, key=f"p_toggle_bk_{k_id}", use_container_width=True):
                core_utils.batch_toggle_media_bookmark([item_id], next_state)
                st.cache_data.clear()
                st.rerun()

        st.divider()
        st.markdown("<span style='color:#EF4444;'>**⚠️ 危險區域**</span>", unsafe_allow_html=True)
        confirm_del = st.checkbox("我確定要解鎖徹底刪除", key=f"p_conf_{k_id}")
        if st.button("💥 執行徹底刪除", key=f"p_del_{k_id}", type="primary", disabled=not confirm_del, use_container_width=True):
            if table_name == "articles": core_utils.delete_article_db(item_id)
            elif table_name == "academic_pubs": core_utils.delete_biblio_db(item_id)
            elif table_name == "media_vault": core_utils.batch_delete_media([item_id])
            st.cache_data.clear() 
            st.rerun()

def render_smart_popover(row, table_name, context=""):
    """對外接口：智慧判斷該渲染為 Popover 還是 Dialog"""
    item_id = row.get('Link') if table_name == "articles" else row.get('id')
    current_title = row.get('Title') or row.get('title') or "未命名"
    current_summary = row.get('Summary') or row.get('abstract') or row.get('summary') or row.get('comment') or row.get('notes') or ""
    is_bk = bool(row.get('is_bookmarked', 0))
    k_id = f"{table_name}_{context}_{item_id}"

    # 🌟 核心路由：將 omni_vault 也導向大型文字編輯 Dialog 視窗
    if table_name in ["custom_resources", "bibliography_notes", "omni_vault"]:
        if st.button("⚙️ 管理", key=f"btn_open_dialog_{k_id}", use_container_width=True):
            _edit_dialog(row, table_name, context, item_id, current_title, current_summary, k_id)
    else:
        _edit_popover(row, table_name, context, item_id, current_title, current_summary, is_bk, k_id)
        
# ==========================================
# 4. 全域批量試算表編輯器 (Batch Data Editor)
# ==========================================
def render_batch_editor(df, table_name, key_prefix=""):
    if df.empty:
        st.info("此分類目前沒有資料可供管理。")
        return

    st.markdown("<div style='background-color:#1E293B; padding:15px; border-radius:10px; margin-bottom:15px;'>", unsafe_allow_html=True)
    st.markdown("##### 🛠️ 資料庫試算表管理模式")
    st.caption("您可以直接在表格中點擊打勾、修改名稱與狀態，最後點擊底部的「儲存所有變更」。")

    df_edit = df.copy()
    df_edit['_id'] = df['Link'] if table_name == "articles" else df['id']
    df_edit.insert(0, 'Select', False) 
    
    if 'is_bookmarked' in df_edit.columns: df_edit['is_bookmarked'] = df_edit['is_bookmarked'].astype(bool)

    if table_name == "custom_resources":
        display_cols = ['Select', 'title', 'url', 'comment', 'added_date']
        disabled_cols = ['url', 'added_date']
    elif table_name == "omni_vault":  # 🌟 加入萬物收藏匣欄位設定
        display_cols = ['Select', 'category', 'title', 'url', 'comment', 'added_date']
        disabled_cols = ['url', 'added_date']
    elif table_name == "media_vault":  
        display_cols = ['Select', 'title', 'creator', 'source_url', 'is_bookmarked']
        disabled_cols = ['source_url', 'creator']
    elif table_name == "academic_pubs":
        display_cols = ['Select', 'title', 'author', 'publisher_journal', 'category', 'is_bookmarked']
        disabled_cols = ['publisher_journal', 'author']
    elif table_name == "bibliography_notes":
        display_cols = ['Select', 'title', 'author', 'importance']
        disabled_cols = ['title', 'author']
    else:
        display_cols = ['Select', 'Title', 'Source', 'Link', 'is_bookmarked']
        disabled_cols = ['Link', 'Source']

    safe_cols = [c for c in display_cols if c in df_edit.columns] + ['_id']
    df_edit = df_edit[safe_cols]

    editor_key = f"editor_{key_prefix}_{table_name}"

    edited_df = st.data_editor(
        df_edit, use_container_width=True, hide_index=True,
        disabled=disabled_cols, height=400, key=editor_key,
        column_config={"_id": None} 
    )

    col1, col2 = st.columns([1, 1])
    
    # 🗑️ 批次刪除邏輯
    with col1:
        selected_count = edited_df['Select'].sum()
        if selected_count == 0:
            st.button("🗑️ 批次刪除 (請先勾選)", disabled=True, use_container_width=True, key=f"del_dummy_{editor_key}")
        else:
            with st.popover(f"🗑️ 徹底刪除已勾選的 {selected_count} 筆資料", use_container_width=True):
                st.error(f"⚠️ 警告：即將從資料庫中永久刪除這 {selected_count} 筆資料。此操作無法復原！")
                if st.button("💥 確認徹底刪除", type="primary", use_container_width=True, key=f"confirm_del_{editor_key}"):
                    selected_rows = edited_df[edited_df['Select'] == True]
                    if not selected_rows.empty:
                        if table_name == "articles":
                            for item_id in selected_rows['_id']: core_utils.delete_article_db(str(item_id))
                        elif table_name == "custom_resources":
                            for item_id in selected_rows['_id']: core_utils.delete_custom_resource(int(item_id))
                        elif table_name == "omni_vault": # 🌟 萬物收藏匣批次刪除
                            for item_id in selected_rows['_id']: core_utils.delete_omni_item(int(item_id))
                        elif table_name == "media_vault":
                            ids_to_delete = [int(x) for x in selected_rows['_id']]
                            core_utils.batch_delete_media(ids_to_delete)
                        elif table_name == "academic_pubs":
                            for item_id in selected_rows['_id']: core_utils.delete_biblio_db(int(item_id))
                        elif table_name == "bibliography_notes":
                            for item_id in selected_rows['_id']: core_utils.delete_bibliography_reference(int(item_id))
                        
                        st.cache_data.clear()
                        st.success("✅ 批次刪除完成！")
                        st.rerun()

    # 💾 批次儲存邏輯
    with col2:
        if st.button("💾 儲存所有文字與狀態修改", use_container_width=True, key=f"save_btn_{editor_key}"):
            changes_applied = 0
            for idx in edited_df.index:
                row_edit = edited_df.loc[idx]
                row_orig = df_edit.loc[idx]
                changed = any(row_edit[col] != row_orig[col] for col in safe_cols if col not in ['Select', '_id'])
                        
                if changed:
                    raw_id = row_edit['_id']
                    item_id = str(raw_id) if table_name == "articles" else int(raw_id)
                    
                    if table_name == "custom_resources":
                        orig_c = df.loc[idx, 'comment'] if 'comment' in df.columns else ""
                        new_c = row_edit.get('comment', orig_c)
                        core_utils.update_custom_resource(item_id, str(row_edit['title']), str(new_c) if pd.notna(new_c) else "")

                    elif table_name == "omni_vault": # 🌟 萬物收藏匣批次儲存
                        orig_c = df.loc[idx, 'comment'] if 'comment' in df.columns else ""
                        new_c = row_edit.get('comment', orig_c)
                        core_utils.update_omni_item(item_id, str(row_edit['category']), str(row_edit['title']), str(new_c) if pd.notna(new_c) else "")
                    
                    elif table_name == "media_vault":
                        orig_s = df.loc[idx, 'summary'] if 'summary' in df.columns else ""
                        core_utils.update_media_vault_meta(item_id, str(row_edit['title']), str(orig_s) if pd.notna(orig_s) else "")
                        if 'is_bookmarked' in row_edit and row_edit['is_bookmarked'] != row_orig['is_bookmarked']:
                            core_utils.batch_toggle_media_bookmark([item_id], int(row_edit['is_bookmarked']))
                            
                    elif table_name == "academic_pubs":
                        orig_a = df.loc[idx, 'abstract'] if 'abstract' in df.columns else ""
                        core_utils.update_academic_pub_meta(item_id, str(row_edit['title']), str(orig_a) if pd.notna(orig_a) else "")
                        if 'category' in row_edit and row_edit['category'] != row_orig['category']:
                            core_utils.update_biblio_category(item_id, str(row_edit['category']))
                        if 'is_bookmarked' in row_edit and row_edit['is_bookmarked'] != row_orig['is_bookmarked']:
                            core_utils.toggle_biblio_bookmark_db(item_id, int(row_orig['is_bookmarked']))
                            
                    elif table_name == "articles":
                        core_utils.update_article_meta(item_id, str(row_edit['Title']))
                        if 'is_bookmarked' in row_edit and row_edit['is_bookmarked'] != row_orig['is_bookmarked']:
                            core_utils.toggle_bookmark_db(item_id, int(row_orig['is_bookmarked']))
                            
                    elif table_name == "bibliography_notes":
                        orig_n = df.loc[idx, 'notes'] if 'notes' in df.columns else ""
                        core_utils.update_bibliography_reference(item_id, str(row_edit.get('importance', '待讀')), str(orig_n))
                    
                    changes_applied += 1
            
            if changes_applied > 0:
                st.cache_data.clear() 
                st.success(f"✅ 成功儲存 {changes_applied} 筆修改！")
            else: st.info("未偵測到任何修改。")
            st.rerun()
            
    st.markdown("</div>", unsafe_allow_html=True)
