import streamlit as st
import math
import pandas as pd
import core_utils 

# ==========================================
# 0. 全域智慧排序引擎 (Universal Smart Sorter)
# ==========================================
def apply_smart_sort(df, table_name, context_key=""):
    """
    全域通用的排序選擇器與處理引擎。
    會根據不同的資料表 (table_name) 提供專屬的排序選項，並回傳排好序的 DataFrame。
    支援動態反轉排序方向 (Toggle)。
    """
    if df.empty:
        return df

    # 定義各資料表支援的排序邏輯 (顯示文字: (對應的資料庫欄位, 預設是否為升冪/順序))
    sort_options = {
        "articles": {
            "擷取時間": ('SortDate', False),  # 預設 False = 新到舊
            "標題": ('Title', True)         # 預設 True = A 到 Z
        },
        "academic_pubs": {
            "加入日期": ('added_date', False) if 'added_date' in df.columns else ('publish_date', False),
            "出版日期": ('publish_date', False),
            "標題": ('title', True),
            "作者": ('author', True)
        },
        "media_vault": {
            "加入日期": ('sort_date', False),
            "標題": ('title', True),
            "導演/創作者": ('creator', True)
        },
        "omni_vault": {
            "加入日期": ('added_date', False),
            "標題": ('title', True),
            "分類名稱": ('category', True)
        },
        "custom_resources": {
            "加入日期": ('added_date', False),
            "標題": ('title', True)
        },
        "bibliography_notes": {
            "加入日期": ('added_date', False),
            "評級高低": ('importance', True), # 預設 True = S 到 C-
            "出版日期": ('publish_date', False),
            "標題": ('title', True)
        }
    }

    # 取得當前資料表支援的選項
    current_options = sort_options.get(table_name, {"預設排序": (df.columns[0], True)})
    option_names = list(current_options.keys())

    # 🌟 UI 佈局：左側留白，中間放滑動按鈕，右側放下拉選單
    col_empty, col_toggle, col_sort = st.columns([6, 1.5, 2.5])
    
    with col_sort:
        selected_sort = st.selectbox(
            "🔀 排序欄位", 
            options=option_names, 
            key=f"sort_field_{table_name}_{context_key}",
            label_visibility="collapsed"
        )
        
    # 抓取該欄位的原始預設方向
    sort_col, default_asc = current_options[selected_sort]
    
    with col_toggle:
        # 🌟 實作滑動開關
        # 如果使用者打開開關，is_reverse 會變成 True
        is_reverse = st.toggle("🔄 反轉排序", key=f"sort_rev_{table_name}_{context_key}")
        
    # 🌟 核心邏輯：如果反轉被開啟，就把預設方向反轉 (not default_asc)
    final_asc = not default_asc if is_reverse else default_asc

    # 執行排序邏輯
    if selected_sort == "評級高低" and table_name == "bibliography_notes":
        imp_map = {"S": 1, "A": 2, "A-": 3, "B": 4, "B-": 5, "C": 6, "C-": 7, "待讀": 8}
        df_sorted = df.copy()
        df_sorted['sort_val'] = df_sorted['importance'].map(imp_map).fillna(9)
        # 根據 final_asc 決定要 S->C 還是 C->S
        df_sorted = df_sorted.sort_values(by=['sort_val', 'added_date'], ascending=[final_asc, not final_asc])
        df_sorted = df_sorted.drop(columns=['sort_val'])
    else:
        actual_col = sort_col
        if sort_col not in df.columns:
            if sort_col.capitalize() in df.columns: actual_col = sort_col.capitalize()
            elif sort_col.lower() in df.columns: actual_col = sort_col.lower()
            else: return df

        # 根據最終計算出的 final_asc 來進行排序
        if df[actual_col].dtype == 'object':
            df_sorted = df.sort_values(by=actual_col, key=lambda col: col.str.lower(), ascending=final_asc)
        else:
            df_sorted = df.sort_values(by=actual_col, ascending=final_asc)

    return df_sorted


# ==========================================
# 0.5 萬能局域文字快篩 (Universal Local Search)
# ==========================================
def apply_local_search(df, search_query):
    """
    接收一個 DataFrame 與搜尋字串。
    利用 Pandas 進行全欄位 (包含標題、摘要、作者等) 的無大小寫差異文字快篩。
    """
    if df.empty or not search_query or str(search_query).strip() == "":
        return df

    search_query = str(search_query).strip()
    
    # 建立一個全為 False 的遮罩 (Mask)
    mask = pd.Series(False, index=df.index)
    
    # 遍歷 DataFrame 的所有文字欄位進行比對
    for col in df.columns:
        # 只針對內容可能是字串的欄位進行搜尋
        if df[col].dtype == object or df[col].dtype == str:
            mask |= df[col].astype(str).str.contains(search_query, case=False, na=False)
            
    return df[mask]

# ==========================================
# 1. 全域分頁引擎 (Universal Pagination)
# ==========================================
# ==========================================
# 1. 全域分頁引擎 (Universal Pagination)
# ==========================================
def paginate_data(data, per_page, session_key):
    total_items = len(data)
    if total_items == 0: return data, 0, 1

    total_pages = max(1, math.ceil(total_items / per_page))
    if session_key not in st.session_state: st.session_state[session_key] = 1

    # 🌟 防護網一：強制校正 Session State 的異常數值 (防止連點導致 < 1)
    if st.session_state[session_key] < 1:
        st.session_state[session_key] = 1
    elif st.session_state[session_key] > total_pages:
        st.session_state[session_key] = total_pages

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
            # 🌟 防護網二：寫入前強制鎖定下限為 1 (max)
            st.session_state[session_key] = max(1, st.session_state[session_key] - 1)
            st.rerun()
            
    with col_page:
        def update_page(): st.session_state[session_key] = st.session_state[f"{session_key}_selector"]
        
        # 🌟 防護網三：嚴格約束 selectbox 的 index 絕對在 0 到 total_pages-1 之間
        safe_index = max(0, min(current_page - 1, total_pages - 1))
        
        st.selectbox("📄 選擇頁數：", range(1, total_pages + 1), index=safe_index, key=f"{session_key}_selector", on_change=update_page, label_visibility="collapsed")
        
    with col_next:
        if st.button("下一頁 ➡️", disabled=(current_page >= total_pages), key=f"next_{session_key}", use_container_width=True):
            # 🌟 防護網四：寫入前強制鎖定上限為 total_pages (min)
            st.session_state[session_key] = min(total_pages, st.session_state[session_key] + 1)
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
# 3. 智慧管理按鈕 (對接終極 CRUD 引擎)
# ==========================================
@st.dialog("⚙️ 項目管理與編輯 (進階)")
def _edit_dialog(row, table_name, context, item_id, current_title, current_summary, k_id, id_col):
    """【軌道 A】用於大量文字編輯的獨立大型視窗"""
    st.markdown(f"**(ID: `{str(item_id)[:20]}...`)**")
    
    if table_name == "custom_resources":
        edit_title = st.text_input("修改名稱:", value=current_title, key=f"d_t_{k_id}")
        edit_summary = st.text_area("說明文字:", value=current_summary, key=f"d_c_{k_id}", height=250)
        if st.button("💾 儲存修改", key=f"d_save_{k_id}", use_container_width=True, type="primary"):
            core_utils.update_record(table_name, item_id, id_column=id_col, title=edit_title, comment=edit_summary)
            st.rerun()

    elif table_name == "omni_vault":
        edit_cat = st.text_input("分類標籤 (可自訂):", value=row.get('category', ''), key=f"d_cat_{k_id}")
        edit_title = st.text_input("修改名稱:", value=current_title, key=f"d_t_{k_id}")
        edit_image = st.text_input("圖片網址 (選填):", value=row.get('image_url', ''), key=f"d_img_{k_id}")
        edit_summary = st.text_area("說明文字/筆記:", value=current_summary, key=f"d_c_{k_id}", height=200)
        if st.button("💾 儲存修改", key=f"d_save_{k_id}", use_container_width=True, type="primary"):
            core_utils.update_record(table_name, item_id, id_column=id_col, category=edit_cat, title=edit_title, image_url=edit_image, comment=edit_summary)
            st.rerun()

    elif table_name == "bibliography_notes":
        edit_title = st.text_input("修改標題:", value=current_title, key=f"d_t_{k_id}")
        current_imp = row.get('importance', '待讀')
        valid_imps = ["S", "A", "A-", "B", "B-", "C", "C-", "待讀"]
        edit_imp = st.selectbox("評級 (Importance):", valid_imps, index=valid_imps.index(current_imp) if current_imp in valid_imps else 7, key=f"d_imp_{k_id}")
        edit_notes = st.text_area("備註 (Notes):", value=row.get('notes', ''), key=f"d_n_{k_id}", height=300)
        if st.button("💾 儲存修改", key=f"d_save_{k_id}", use_container_width=True, type="primary"):
            core_utils.update_record(table_name, item_id, id_column=id_col, title=edit_title, importance=edit_imp, notes=edit_notes)
            st.rerun()

    st.divider()
    st.markdown("<span style='color:#EF4444;'>**⚠️ 危險區域**</span>", unsafe_allow_html=True)
    confirm_del = st.checkbox("我確定要解鎖徹底刪除", key=f"d_conf_{k_id}")
    if st.button("💥 執行徹底刪除", key=f"d_del_{k_id}", type="primary", disabled=not confirm_del, use_container_width=True):
        core_utils.delete_records(table_name, [item_id], id_column=id_col)
        st.rerun()


def _edit_popover(row, table_name, context, item_id, current_title, current_summary, is_bk, k_id, id_col):
    """【軌道 B】用於快速編輯的輕量級氣泡視窗"""
    with st.popover("⚙️ 管理", use_container_width=True):
        st.markdown(f"**📝 編輯項目** (ID: `{str(item_id)[:15]}...`)")
        edit_title = st.text_input("手動改名:", value=current_title, key=f"p_t_{k_id}")
        
        edit_summary = current_summary
        if table_name in ["academic_pubs", "media_vault"]:
            edit_summary = st.text_area("修改摘要/簡介:", value=current_summary, key=f"p_c_{k_id}", height=100)
        
        new_cat = None
        if context == "bookshelf":
            current_cat = row.get('category', '未分類')
            valid_cats = ["未分類", "研究", "學術", "小說", "詩", "次文化", "藝術", "音樂"]
            new_cat = st.selectbox("📚 變更書架分類：", valid_cats, index=valid_cats.index(current_cat) if current_cat in valid_cats else 0, key=f"p_cat_{k_id}")

        if st.button("💾 儲存文字變更", key=f"p_save_{k_id}", use_container_width=True, type="primary"):
            kwargs = {}
            if table_name == "articles": kwargs['Title'] = edit_title
            elif table_name == "media_vault": kwargs.update({'title': edit_title, 'summary': edit_summary})
            elif table_name == "academic_pubs": 
                kwargs.update({'title': edit_title, 'abstract': edit_summary})
                if new_cat: kwargs['category'] = new_cat
            core_utils.update_record(table_name, item_id, id_column=id_col, **kwargs)
            st.rerun()

        st.divider()
        st.markdown("**⭐ 狀態管理**")
        btn_label = "💔 移出書架" if context == "bookshelf" else ("💔 移除收藏" if is_bk else "❤️ 加入收藏")
        if table_name == "media_vault": btn_label = "✅ 標記為已完食" if is_bk else "⏳ 退回待播清單"
        
        if st.button(btn_label, key=f"p_toggle_bk_{k_id}", use_container_width=True):
            next_state = 0 if is_bk else 1
            core_utils.toggle_bookmark(table_name, [item_id], next_state, id_column=id_col)
            st.rerun()

        st.divider()
        st.markdown("<span style='color:#EF4444;'>**⚠️ 危險區域**</span>", unsafe_allow_html=True)
        confirm_del = st.checkbox("我確定要解鎖徹底刪除", key=f"p_conf_{k_id}")
        if st.button("💥 執行徹底刪除", key=f"p_del_{k_id}", type="primary", disabled=not confirm_del, use_container_width=True):
            core_utils.delete_records(table_name, [item_id], id_column=id_col)
            st.rerun()

def render_smart_popover(row, table_name, context=""):
    """對外接口：智慧判斷渲染軌道"""
    id_col = "Link" if table_name == "articles" else "id"
    item_id = str(row.get(id_col)) if table_name == "articles" else int(row.get(id_col, 0))
    current_title = row.get('Title') or row.get('title') or "未命名"
    current_summary = row.get('Summary') or row.get('abstract') or row.get('summary') or row.get('comment') or row.get('notes') or ""
    is_bk = bool(row.get('is_bookmarked', 0))
    k_id = f"{table_name}_{context}_{item_id}"

    if table_name in ["custom_resources", "bibliography_notes", "omni_vault"]:
        if st.button("⚙️ 管理", key=f"btn_open_dialog_{k_id}", use_container_width=True):
            _edit_dialog(row, table_name, context, item_id, current_title, current_summary, k_id, id_col)
    else:
        _edit_popover(row, table_name, context, item_id, current_title, current_summary, is_bk, k_id, id_col)
        
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
    id_col = "Link" if table_name == "articles" else "id"
    df_edit['_id'] = df[id_col]
    df_edit.insert(0, 'Select', False) 
    
    if 'is_bookmarked' in df_edit.columns: df_edit['is_bookmarked'] = df_edit['is_bookmarked'].astype(bool)

    # 欄位顯示設定
    if table_name == "custom_resources":
        display_cols, disabled_cols = ['Select', 'title', 'url', 'comment', 'added_date'], ['url', 'added_date']
    elif table_name == "omni_vault":
        display_cols, disabled_cols = ['Select', 'category', 'title', 'url', 'image_url', 'comment', 'added_date'], ['url', 'added_date']
    elif table_name == "media_vault":  
        display_cols, disabled_cols = ['Select', 'title', 'creator', 'source_url', 'is_bookmarked'], ['source_url', 'creator']
    elif table_name == "academic_pubs":
        display_cols, disabled_cols = ['Select', 'title', 'author', 'publisher_journal', 'category', 'is_bookmarked'], ['publisher_journal', 'author']
    elif table_name == "bibliography_notes":
        display_cols, disabled_cols = ['Select', 'title', 'author', 'importance', 'notes'], ['title', 'author']
    else:
        display_cols, disabled_cols = ['Select', 'Title', 'Source', 'Link', 'is_bookmarked'], ['Link', 'Source']

    safe_cols = [c for c in display_cols if c in df_edit.columns] + ['_id']
    df_edit = df_edit[safe_cols]
    editor_key = f"editor_{key_prefix}_{table_name}"

    edited_df = st.data_editor(
        df_edit, use_container_width=True, hide_index=True,
        disabled=disabled_cols, height=400, key=editor_key, column_config={"_id": None} 
    )

    col1, col2 = st.columns([1, 1])
    
    # 🗑️ 全域一行刪除
    with col1:
        selected_count = edited_df['Select'].sum()
        if selected_count == 0:
            st.button("🗑️ 批次刪除 (請先勾選)", disabled=True, use_container_width=True, key=f"del_dummy_{editor_key}")
        else:
            with st.popover(f"🗑️ 徹底刪除已勾選的 {selected_count} 筆資料", use_container_width=True):
                st.error(f"⚠️ 警告：此操作無法復原！")
                if st.button("💥 確認徹底刪除", type="primary", use_container_width=True, key=f"confirm_del_{editor_key}"):
                    selected_rows = edited_df[edited_df['Select'] == True]
                    target_ids = [str(x) if table_name == "articles" else int(x) for x in selected_rows['_id']]
                    core_utils.delete_records(table_name, target_ids, id_column=id_col)
                    st.rerun()

    # 💾 全域動態組裝更新
    with col2:
        if st.button("💾 儲存所有文字與狀態修改", use_container_width=True, key=f"save_btn_{editor_key}"):
            changes_applied = 0
            for idx in edited_df.index:
                row_edit, row_orig = edited_df.loc[idx], df_edit.loc[idx]
                if any(row_edit[col] != row_orig[col] for col in safe_cols if col not in ['Select', '_id']):
                    item_id = str(row_edit['_id']) if table_name == "articles" else int(row_edit['_id'])
                    kwargs = {}
                    
                    if table_name == "custom_resources":
                        kwargs = {'title': str(row_edit['title']), 'comment': str(row_edit.get('comment', ''))}
                    elif table_name == "omni_vault":
                        kwargs = {'category': str(row_edit['category']), 'title': str(row_edit['title']), 'comment': str(row_edit.get('comment', '')), 'image_url': str(row_edit.get('image_url', ''))}
                    elif table_name == "media_vault":
                        kwargs = {'title': str(row_edit['title'])}
                    elif table_name == "academic_pubs":
                        kwargs = {'title': str(row_edit['title'])}
                        if 'category' in row_edit and row_edit['category'] != row_orig['category']: kwargs['category'] = str(row_edit['category'])
                    elif table_name == "articles":
                        kwargs = {'Title': str(row_edit['Title'])}
                    elif table_name == "bibliography_notes":
                        kwargs = {'importance': str(row_edit.get('importance', '待讀')), 'notes': str(row_edit.get('notes', ''))}

                    # 獨立處理需要 cache_data.clear 的書籤 toggle
                    if 'is_bookmarked' in row_edit and row_edit['is_bookmarked'] != row_orig['is_bookmarked']:
                        core_utils.toggle_bookmark(table_name, [item_id], int(row_edit['is_bookmarked']), id_column=id_col)
                    
                    if kwargs:
                        core_utils.update_record(table_name, item_id, id_column=id_col, **kwargs)
                        
                    changes_applied += 1
            
            if changes_applied > 0: st.success(f"✅ 成功儲存 {changes_applied} 筆修改！")
            else: st.info("未偵測到任何修改。")
            st.rerun()
            
    st.markdown("</div>", unsafe_allow_html=True)
