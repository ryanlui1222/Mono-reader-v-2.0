import streamlit as st
import math
import pandas as pd
import core_utils # 必須引入，因為按鈕要執行資料庫操作

# ==========================================
# 1. 全域分頁引擎 (Universal Pagination) - 兩階段版
# ==========================================
def paginate_data(data, per_page, session_key):
    """
    第一階段：接收 DataFrame 或 List，處理頁碼邏輯並回傳切割後的當頁資料。
    不渲染任何 UI。
    """
    total_items = len(data)
    if total_items == 0:
        return data, 0, 1

    total_pages = max(1, math.ceil(total_items / per_page))

    # 初始化 session_state
    if session_key not in st.session_state:
        st.session_state[session_key] = 1
    
    # 邊界防護
    if st.session_state[session_key] > total_pages:
        st.session_state[session_key] = total_pages

    current_page = st.session_state[session_key]
    start_idx = (current_page - 1) * per_page
    end_idx = start_idx + per_page

    # 切割資料
    if isinstance(data, pd.DataFrame):
        page_data = data.iloc[start_idx:end_idx]
    else:
        page_data = data[start_idx:end_idx]

    return page_data, total_pages, current_page

def render_pagination_ui(total_pages, current_page, session_key):
    """
    第二階段：在列表底部渲染包含「上一頁、選單、下一頁」的分頁控制器。
    """
    if total_pages <= 1:
        return

    st.write("") # 留白
    st.markdown("---")
    
    col_prev, col_page, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if st.button("⬅️ 上一頁", disabled=(current_page <= 1), key=f"prev_{session_key}", use_container_width=True):
            st.session_state[session_key] -= 1
            st.rerun()
            
    with col_page:
        def update_page():
            st.session_state[session_key] = st.session_state[f"{session_key}_selector"]
        
        st.selectbox(
            "📄 選擇頁數：", 
            range(1, total_pages + 1), 
            index=current_page - 1, 
            key=f"{session_key}_selector", 
            on_change=update_page,
            label_visibility="collapsed" # 隱藏標籤讓排版更緊湊
        )
        
    with col_next:
        if st.button("下一頁 ➡️", disabled=(current_page >= total_pages), key=f"next_{session_key}", use_container_width=True):
            st.session_state[session_key] += 1
            st.rerun()

# ==========================================
# 2. 全域網格卡片渲染 (Universal Grid Card)
# ==========================================
def render_grid_card(row):
    """
    統一渲染直立式浮動卡片 (適用於 Media Vault, 待讀書架)
    自動相容大寫 (Monoreader) 與小寫 (Biblioapp) 欄位名稱
    """
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
# 3. 智慧管理按鈕 (Smart CRUD Popover) - 完全體
# ==========================================
def render_smart_popover(row, table_name, context=""):
    """
    全域智慧管理按鈕：一鍵包攬手動改名、摘要修改、收藏切換、變更分類與二次確認刪除。
    自動精準對齊真實資料庫欄位特徵。
    """
    import core_utils # 延遲引入防止循環 import
    
    # 🎯 智慧定位主鍵 (articles 用 Link，其餘用 id)
    item_id = row.get('Link') if table_name == "articles" else row.get('id')
    
    # 🎯 智慧擷取現有文字 (相容大小寫特徵)
    current_title = row.get('Title') or row.get('title') or "未命名"
    current_summary = row.get('Summary') or row.get('abstract') or row.get('summary') or row.get('comment') or ""
    is_bk = bool(row.get('is_bookmarked', 0))

    # 根據不同資料表，定義按鈕的唯一 key 辨識碼，防止 Streamlit 元件 ID 衝突
    k_id = f"{table_name}_{context}_{item_id}"

    with st.popover("⚙️ 管理", use_container_width=True):
        st.markdown(f"**📝 編輯項目** (ID/Link: `{str(item_id)[:15]}...`)")
        
        # 1. 編輯區塊分流
        if table_name == "custom_resources":
            edit_title = st.text_input("修改名稱:", value=current_title, key=f"t_{k_id}")
            edit_summary = st.text_area("說明文字:", value=current_summary, key=f"c_{k_id}", height=100)
            if st.button("💾 儲存修改", key=f"save_{k_id}", use_container_width=True):
                core_utils.update_custom_resource(item_id, edit_title, edit_summary)
                st.rerun()
                
        else:
            # articles, academic_pubs, media_vault 都有改名、改摘要與收藏欄位
            edit_title = st.text_input("手動改名:", value=current_title, key=f"t_{k_id}")
            
            # articles 的摘要是爬蟲洗好的，暫不開放修改；開放學術與影音館的摘要修改
            if table_name in ["academic_pubs", "media_vault"]:
                edit_summary = st.text_area("修改摘要/簡介:", value=current_summary, key=f"c_{k_id}", height=100)
            
            # 📚 特例：待讀書架額外長出「變更分類」選單
            if context == "bookshelf":
                current_cat = row.get('category', '未分類')
                valid_cats = ["未分類", "研究", "學術", "小說", "詩", "次文化", "藝術", "音樂"]
                cat_idx = valid_cats.index(current_cat) if current_cat in valid_cats else 0
                new_cat = st.selectbox("📚 變更書架分類：", valid_cats, index=cat_idx, key=f"cat_{k_id}")

            # 💾 儲存文字與特例變更
            if st.button("💾 儲存文字變更", key=f"save_{k_id}", use_container_width=True, type="primary"):
                if table_name == "articles":
                    core_utils.update_article_meta(item_id, edit_title)
                elif table_name == "academic_pubs":
                    core_utils.update_academic_pub_meta(item_id, edit_title, edit_summary)
                    if context == "bookshelf":
                        core_utils.update_biblio_category(item_id, new_cat)
                elif table_name == "media_vault":
                    core_utils.update_media_vault_meta(item_id, edit_title, edit_summary)
                st.rerun()

            st.divider()
            
            # 2. ❤️ 收藏狀態切換控制
            st.markdown("**⭐ 狀態管理**")
            if table_name == "articles":
                st.button("💔 移除收藏" if is_bk else "❤️ 加入收藏", key=f"toggle_bk_{k_id}", on_click=core_utils.toggle_bookmark_db, args=(item_id, is_bk), use_container_width=True)
            elif table_name == "academic_pubs":
                # 待讀書架點擊移除等於取消最愛書籤
                btn_label = "💔 移出書架" if context == "bookshelf" else ("💔 取消收藏" if is_bk else "❤️ 收藏文獻")
                st.button(btn_label, key=f"toggle_bk_{k_id}", on_click=core_utils.toggle_biblio_bookmark_db, args=(item_id, is_bk), use_container_width=True)
            elif table_name == "media_vault":
                # 1=待看, 0=已完食庫
                mv_label = "✅ 標記為已完食" if is_bk else "⏳ 退回待播清單"
                next_state = 0 if is_bk else 1
                st.button(mv_label, key=f"toggle_bk_{k_id}", on_click=core_utils.batch_toggle_media_bookmark, args=([item_id], next_state), use_container_width=True)

        # 3. 🚨 二次確認徹底刪除
        st.divider()
        st.markdown("<span style='color:#EF4444;'>**⚠️ 危險區域**</span>", unsafe_allow_html=True)
        confirm_del = st.checkbox("我確定要解鎖徹底刪除", key=f"conf_{k_id}")
        
        if st.button("💥 執行徹底刪除", key=f"del_{k_id}", type="primary", disabled=not confirm_del, use_container_width=True):
            if table_name == "articles":
                core_utils.delete_article_db(item_id)
            elif table_name == "academic_pubs":
                core_utils.delete_biblio_db(item_id)
            elif table_name == "media_vault":
                core_utils.batch_delete_media([item_id])
            elif table_name == "custom_resources":
                core_utils.delete_custom_resource(item_id)
            st.rerun()

# ==========================================
# 4. 全域批量試算表編輯器 (Batch Data Editor) - 完全體
# ==========================================
def render_batch_editor(df, table_name, key_prefix=""):
    """
    全域試算表模式。接收 DataFrame，渲染為可勾選/編輯的 Excel 介面。
    具備 Numpy 強制轉型防護與隱藏主鍵追蹤功能，確保 CRUD 操作絕對精準。
    """
    if df.empty:
        st.info("此分類目前沒有資料可供管理。")
        return

    st.markdown("<div style='background-color:#1E293B; padding:15px; border-radius:10px; margin-bottom:15px;'>", unsafe_allow_html=True)
    st.markdown("##### 🛠️ 資料庫試算表管理模式")
    st.caption("您可以直接在表格中點擊打勾、修改名稱與狀態，最後點擊底部的「儲存所有變更」。點擊表頭可排序。")

    df_edit = df.copy()
    
    # 🌟 核心防錯：植入隱藏的絕對主鍵
    df_edit['_id'] = df['id'] if 'id' in df.columns else df['Link']
    
    # 統一把勾選框叫做 'Select'
    df_edit.insert(0, 'Select', False) 
    
    # 🌟 UX 優化：將 1/0 轉換為 True/False，讓試算表顯示為漂亮的打勾方塊
    if 'is_bookmarked' in df_edit.columns:
        df_edit['is_bookmarked'] = df_edit['is_bookmarked'].astype(bool)

    # 根據不同資料表，決定哪些欄位可以顯示與編輯
    if table_name == "custom_resources":
        display_cols = ['Select', 'title', 'url', 'comment', 'added_date']
        disabled_cols = ['url', 'added_date'] # 網址和時間不准改
    elif table_name == "media_vault":  
        display_cols = ['Select', 'title', 'creator', 'source_url', 'is_bookmarked']
        disabled_cols = ['source_url', 'creator'] # 鎖定無法單純儲存的欄位
    elif table_name == "academic_pubs":
        display_cols = ['Select', 'title', 'author', 'publisher_journal', 'category', 'is_bookmarked']
        disabled_cols = ['publisher_journal', 'author']
    else:
        display_cols = ['Select', 'Title', 'Source', 'Link', 'is_bookmarked']
        disabled_cols = ['Link', 'Source']

    # 確保我們要顯示的欄位真的存在於 df 中，並加上我們的隱藏主鍵 _id
    safe_cols = [c for c in display_cols if c in df_edit.columns] + ['_id']
    df_edit = df_edit[safe_cols]

    editor_key = f"editor_{key_prefix}_{table_name}"

    # 渲染編輯器
    edited_df = st.data_editor(
        df_edit,
        use_container_width=True,
        hide_index=True,
        disabled=disabled_cols,
        height=400,
        key=editor_key,
        column_config={"_id": None}  # 🌟 告訴 Streamlit 隱藏這個欄位，但內部要記住
    )

    col1, col2 = st.columns([1, 1])
    
    # ==========================
    # 🗑️ 批次刪除邏輯
    # ==========================
    with col1:
        selected_count = edited_df['Select'].sum()
        if st.button(f"🗑️ 徹底刪除已勾選的 {selected_count} 筆資料", type="primary", disabled=(selected_count == 0), use_container_width=True, key=f"del_btn_{editor_key}"):
            selected_rows = edited_df[edited_df['Select'] == True]
            if not selected_rows.empty:
                # 🛡️ 轉型防護網：強制將 Numpy Int64 轉為 Python 原生 int/str
                if table_name == "articles":
                    for item_id in selected_rows['_id']: core_utils.delete_article_db(str(item_id))
                elif table_name == "custom_resources":
                    for item_id in selected_rows['_id']: core_utils.delete_custom_resource(int(item_id))
                elif table_name == "media_vault":
                    ids_to_delete = [int(x) for x in selected_rows['_id']]
                    core_utils.batch_delete_media(ids_to_delete)
                elif table_name == "academic_pubs":
                    for item_id in selected_rows['_id']: core_utils.delete_biblio_db(int(item_id))
                
                st.cache_data.clear() # 🌟 強制清除快取，確保表格立刻更新
                st.success("✅ 批次刪除完成！")
                st.rerun()

    # ==========================
    # 💾 批次儲存編輯邏輯
    # ==========================
    with col2:
        if st.button("💾 儲存所有文字與狀態修改", use_container_width=True, key=f"save_btn_{editor_key}"):
            changes_applied = 0
            
            # 遍歷表格，找出與原始資料不同的列
            for idx in edited_df.index:
                row_edit = edited_df.loc[idx]
                row_orig = df_edit.loc[idx]
                
                changed = False
                for col in safe_cols:
                    if col in ['Select', '_id']: continue # 略過核取框與主鍵比對
                    if row_edit[col] != row_orig[col]:
                        changed = True
                        break
                        
                if changed:
                    raw_id = row_edit['_id']
                    # 🛡️ 轉型防護網：Turso 嚴格要求原生 Python 型態
                    item_id = str(raw_id) if table_name == "articles" else int(raw_id)
                    
                    if table_name == "custom_resources":
                        orig_c = df.loc[idx, 'comment'] if 'comment' in df.columns else ""
                        new_c = row_edit.get('comment', orig_c)
                        core_utils.update_custom_resource(item_id, str(row_edit['title']), str(new_c) if pd.notna(new_c) else "")
                    
                    elif table_name == "media_vault":
                        orig_s = df.loc[idx, 'summary'] if 'summary' in df.columns else ""
                        core_utils.update_media_vault_meta(item_id, str(row_edit['title']), str(orig_s) if pd.notna(orig_s) else "")
                        
                        if 'is_bookmarked' in row_edit and row_edit['is_bookmarked'] != row_orig['is_bookmarked']:
                            # Media Vault 的 API 是直接吃目標狀態
                            core_utils.batch_toggle_media_bookmark([item_id], int(row_edit['is_bookmarked']))
                            
                    elif table_name == "academic_pubs":
                        orig_a = df.loc[idx, 'abstract'] if 'abstract' in df.columns else ""
                        core_utils.update_academic_pub_meta(item_id, str(row_edit['title']), str(orig_a) if pd.notna(orig_a) else "")
                        
                        if 'category' in row_edit and row_edit['category'] != row_orig['category']:
                            core_utils.update_biblio_category(item_id, str(row_edit['category']))
                        
                        if 'is_bookmarked' in row_edit and row_edit['is_bookmarked'] != row_orig['is_bookmarked']:
                            # ⚠️ 雙重反轉破解：傳入原始狀態，讓後端將其反轉為新狀態
                            core_utils.toggle_biblio_bookmark_db(item_id, int(row_orig['is_bookmarked']))
                            
                    elif table_name == "articles":
                        core_utils.update_article_meta(item_id, str(row_edit['Title']))
                        
                        if 'is_bookmarked' in row_edit and row_edit['is_bookmarked'] != row_orig['is_bookmarked']:
                            # ⚠️ 雙重反轉破解：傳入原始狀態
                            core_utils.toggle_bookmark_db(item_id, int(row_orig['is_bookmarked']))
                    
                    changes_applied += 1
            
            if changes_applied > 0:
                st.cache_data.clear() # 🌟 寫入後強制洗掉暫存
                st.success(f"✅ 成功儲存 {changes_applied} 筆修改！")
            else:
                st.info("未偵測到任何修改。")
                
            st.rerun()
            
    st.markdown("</div>", unsafe_allow_html=True)
