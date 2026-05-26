import streamlit as st
import core_utils
import pandas as pd
import math

def render_media_gallery(media_list, tab_name, style_type="movie"):
    """通用的畫廊渲染器：處理分頁、UI排版與批量管理的核取方塊"""
    if not media_list:
        st.info("目前尚無收藏。")
        return
        
    ITEMS_PER_PAGE = 20
    total_pages = max(1, math.ceil(len(media_list) / ITEMS_PER_PAGE))
    page_key = f"{tab_name}_page"
    
    if page_key not in st.session_state:
        st.session_state[page_key] = 1
    if st.session_state[page_key] > total_pages:
        st.session_state[page_key] = total_pages
        
    current_page = st.session_state[page_key]
    start_idx = (current_page - 1) * ITEMS_PER_PAGE
    page_items = media_list[start_idx : start_idx + ITEMS_PER_PAGE]
    
    # === 渲染卡片畫廊 ===
    cols = st.columns(5)
    for i, row in enumerate(page_items):
        col_idx = i % 5
        with cols[col_idx]:
            with st.container(border=True):
                
                # [管理模式] 核取方塊
                if st.session_state.get("media_edit_mode", False):
                    # 使用 Callback 防止 Streamlit 重刷新丟失狀態
                    def toggle_cb(m_id):
                        if st.session_state[f"sel_{m_id}"]:
                            if m_id not in st.session_state.selected_media:
                                st.session_state.selected_media.append(m_id)
                        else:
                            if m_id in st.session_state.selected_media:
                                st.session_state.selected_media.remove(m_id)
                                
                    is_selected = (row['id'] in st.session_state.get('selected_media', []))
                    st.checkbox("勾選選取", value=is_selected, key=f"sel_{row['id']}", on_change=toggle_cb, args=(row['id'],))
                
                # 封面渲染
                cover = row.get('cover_image')
                if cover and str(cover).startswith('data:image'):
                    if style_type == "music":
                        st.markdown(f'<img src="{cover}" width="100%" style="border-radius:50%; box-shadow: 2px 2px 10px rgba(0,0,0,0.5); margin-bottom:10px;"/>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<img src="{cover}" width="100%" style="border-radius:8px; margin-bottom:10px;"/>', unsafe_allow_html=True)
                else:
                    st.info("無圖片")
                
                # 標題與最愛星號
                star = "⭐ " if str(row.get('is_bookmarked')) == '1' else ""
                st.markdown(f"**{star}[{row.get('title', '未知')}]({row.get('source_url', '#')})**")
                
                # 副標題/導演
                if style_type == "movie":
                    st.caption(f"🎬 {str(row.get('creator', '未知導演'))[:30]}")
                else:
                    st.caption(f"🎵 {str(row.get('creator', '未知音樂家'))[:30]}")
                
    # === 底部分頁控制列 ===
    st.markdown("---")
    pc1, pc2, pc3 = st.columns([2, 6, 2])
    with pc1:
        if st.button("⬅️ 上一頁", disabled=(current_page == 1), key=f"prev_{tab_name}", use_container_width=True):
            st.session_state[page_key] -= 1
            st.rerun()
    with pc2:
        st.markdown(f"<div style='text-align:center; padding-top: 8px;'>第 <b>{current_page}</b> 頁 / 共 <b>{total_pages}</b> 頁</div>", unsafe_allow_html=True)
    with pc3:
        if st.button("下一頁 ➡️", disabled=(current_page == total_pages), key=f"next_{tab_name}", use_container_width=True):
            st.session_state[page_key] += 1
            st.rerun()

def render_page():
    # 初始化狀態
    if "selected_media" not in st.session_state:
        st.session_state.selected_media = []

    # === 頁面標題與全局管理開關 ===
    col_h1, col_h2 = st.columns([7, 3])
    with col_h1:
        st.header("🎬 影音與網路資源館 (Media Vault)")
    with col_h2:
        st.write("") # 微調對齊
        # 開啟批量管理模式
        if st.toggle("🛠️ 啟用批量管理模式", key="media_edit_mode"):
            pass # 狀態自動綁定
        else:
            # 關閉時清空選取
            st.session_state.selected_media = []
            st.session_state.show_delete_confirm = False

    st.caption("收納跨越文本之外的影視地圖、專輯聲響與社群分享卡片。")
    
    # === 管理模式工具列 (浮動區塊) ===
    if st.session_state.get("media_edit_mode", False):
        st.markdown("<div style='background-color:#f0f2f6; padding:15px; border-radius:10px;'>", unsafe_allow_html=True)
        
        if st.session_state.get("show_delete_confirm", False):
            st.warning(f"⚠️ 警告：確定要徹底刪除選取的 {len(st.session_state.selected_media)} 個項目嗎？此操作無法還原！")
            c1, c2 = st.columns(2)
            if c1.button("✅ 確認徹底刪除", type="primary", use_container_width=True):
                if st.session_state.selected_media:
                    core_utils.batch_delete_media(st.session_state.selected_media)
                    st.session_state.selected_media = []
                st.session_state.show_delete_confirm = False
                st.rerun()
            if c2.button("❌ 取消", use_container_width=True):
                st.session_state.show_delete_confirm = False
                st.rerun()
        else:
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            with c1:
                st.markdown(f"**批量管理** (目前已選: {len(st.session_state.selected_media)} 項)")
            with c2:
                if st.button("⭐ 加入最愛", use_container_width=True, disabled=len(st.session_state.selected_media)==0):
                    core_utils.batch_toggle_media_bookmark(st.session_state.selected_media, 1)
                    st.session_state.selected_media = []
                    st.rerun()
            with c3:
                if st.button("💔 移除最愛", use_container_width=True, disabled=len(st.session_state.selected_media)==0):
                    core_utils.batch_toggle_media_bookmark(st.session_state.selected_media, 0)
                    st.session_state.selected_media = []
                    st.rerun()
            with c4:
                if st.button("🗑️ 刪除勾選項", type="primary", use_container_width=True, disabled=len(st.session_state.selected_media)==0):
                    st.session_state.show_delete_confirm = True
                    st.rerun()
        st.markdown("</div><br>", unsafe_allow_html=True)

    st.markdown("---")
    
    tab_movie, tab_music, tab_resource = st.tabs(["🎬 電影與影集", "🎵 音樂與專輯", "🌐 網路資源分享卡"])

    # ====================================================================
    # 🎬 分頁一：電影與影集
    # ====================================================================
    with tab_movie:
        st.markdown("### 📥 引入電影文獻")
        col_m_in, col_m_btn = st.columns([5, 1])
        with col_m_in:
            movie_input = st.text_input("輸入 IMDb 網址或 ID：", placeholder="例如貼上 IMDb 網址，或輸入 tt4003440", label_visibility="collapsed")
        with col_m_btn:
            if st.button("加入電影庫", use_container_width=True, type="primary"):
                if movie_input:
                    with st.spinner("正在呼叫 TMDB API 解鎖數據與導演..."):
                        m_data = core_utils.fetch_movie_data(movie_input)
                        if m_data:
                            core_utils.insert_media_db(m_data) 
                            st.success(f"🎬 已成功加入：{m_data['title']}")
                            st.rerun()
                        else:
                            st.error("❌ 抓取失敗，請確認網址或稍後再試。")
        
        st.divider()
        st.markdown("### 🍿 我的電影庫")
        movies = core_utils.fetch_media_by_broad_type("Movie")
        render_media_gallery(movies, tab_name="movie", style_type="movie")

    # ====================================================================
    # 🎵 分頁二：音樂與專輯
    # ====================================================================
    with tab_music:
        st.markdown("### 📥 引入音樂文獻")
        col_mu_in, col_mu_btn = st.columns([5, 1])
        with col_mu_in:
            music_input = st.text_input("輸入 Apple Music 網址或 ID：", placeholder="支援全區 Apple Music 網址", label_visibility="collapsed")
        with col_mu_btn:
            if st.button("加入音樂庫", use_container_width=True, type="primary"):
                if music_input:
                    with st.spinner("正在跨區輪詢 Apple Music API..."):
                        mu_data = core_utils.fetch_apple_music_data(music_input)
                        if mu_data:
                            core_utils.insert_media_db(mu_data)
                            st.success(f"🎵 已成功加入：{mu_data['title']}")
                            st.rerun()
                        else:
                            st.error("❌ 抓取失敗，找不到此專輯。")
        
        st.divider()
        st.markdown("### 🎧 我的音樂櫃")
        music_list = core_utils.fetch_media_by_broad_type("Music")
        render_media_gallery(music_list, tab_name="music", style_type="music")

    # ====================================================================
    # 🌐 分頁三：網路資源分享卡 (維持原有設計)
    # ====================================================================
    with tab_resource:
        st.markdown("### 🌐 快收網路社群與卡片連結")
        st.caption("此分頁適合備存 Twitter、Facebook 貼文。")
        
        col_res_in, col_res_btn = st.columns([5, 1])
        with col_res_in:
            res_url = st.text_input("貼上社群或外部資源網址：", placeholder="https://x.com/...", label_visibility="collapsed", key="res_in_key")
        with col_res_btn:
            if st.button("快存卡片", use_container_width=True, type="primary", key="res_btn_key"):
                if res_url.startswith("http"):
                    with st.spinner("正在快取分享卡片資訊..."):
                        if core_utils.add_custom_resource("media_vault", res_url):
                            st.success("🌐 分享卡片已加入備存清單！")
                            st.rerun()
                else: st.warning("請輸入完整的 http 網址。")
        
        st.markdown("---")
        
        df_res = core_utils.fetch_custom_resources("media_vault")
        if df_res is None or df_res.empty:
            st.info("📦 目前還沒有儲存任何社群資源卡片。")
        else:
            for _, row in df_res.iterrows():
                with st.container():
                    col_card_meta, col_card_opt = st.columns([5, 1])
                    with col_card_meta:
                        st.markdown(f"#### [{row.get('title', '無標題')}]({row.get('url', '#')})")
                        st.caption(f"🔗 來源網址: {row.get('url', '#')}")
                        if pd.notna(row.get('comment')) and str(row.get('comment')).strip():
                            st.info(row['comment'])
                            
                    with col_card_opt:
                        with st.popover("⚙️ 管理卡片", use_container_width=True):
                            new_title = st.text_input("修改名稱:", value=row.get('title', ''), key=f"edit_t_{row['id']}")
                            current_comment = row.get('comment', '') if pd.notna(row.get('comment')) else ""
                            new_comment = st.text_area("添加備註:", value=current_comment, key=f"edit_c_{row['id']}")
                            
                            if st.button("💾 保存修改", key=f"save_c_{row['id']}", use_container_width=True):
                                core_utils.update_custom_resource(row['id'], new_title, new_comment)
                                st.rerun()
                                
                            st.divider()
                            if st.button("🗑️ 徹底刪除", key=f"del_card_{row['id']}", type="primary", use_container_width=True):
                                core_utils.delete_custom_resource(row['id'])
                                st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)
