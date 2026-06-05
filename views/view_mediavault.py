import streamlit as st
import core_utils
import pandas as pd
from views import ui_components  # 🌟 引入全域元件

def render_media_gallery(media_list, tab_name, style_type="movie", current_view_state=1):
    """通用的畫廊渲染器：處理UI排版與批量管理的核取方塊 (分頁已交由 ui_components 處理)"""
    if not media_list:
        st.info("📦 此清單目前尚無收藏。")
        return
        
    page_key = f"{tab_name}_{current_view_state}_page"
    
    # 🌟 套用全域分頁引擎
    page_items = ui_components.get_paginated_data(media_list, per_page=20, session_key=page_key)
    
    # === 渲染卡片畫廊 ===
    cols = st.columns(5)
    for i, row in enumerate(page_items):
        col_idx = i % 5
        with cols[col_idx]:
            with st.container(border=True):
                # [管理模式] 核取方塊
                if st.session_state.get("media_edit_mode", False):
                    def toggle_cb(m_id):
                        if st.session_state[f"sel_{m_id}"]:
                            if m_id not in st.session_state.selected_media:
                                st.session_state.selected_media.append(m_id)
                        else:
                            if m_id in st.session_state.selected_media:
                                st.session_state.selected_media.remove(m_id)
                                
                    is_selected = (row['id'] in st.session_state.get('selected_media', []))
                    st.checkbox("勾選選取", value=is_selected, key=f"sel_{row['id']}", on_change=toggle_cb, args=(row['id'],))
                
                # 封面渲染 (保留音樂特有圓角)
                cover = row.get('cover_image')
                if cover and str(cover).startswith('data:image'):
                    if style_type == "music":
                        st.markdown(f'<img src="{cover}" width="100%" style="border-radius:50%; box-shadow: 2px 2px 10px rgba(0,0,0,0.5); margin-bottom:10px;"/>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<img src="{cover}" width="100%" style="border-radius:8px; margin-bottom:10px;"/>', unsafe_allow_html=True)
                else:
                    st.info("無圖片")
                
                # 標題與狀態符號 (1為待看，0為已完食)
                status_icon = "⏳ " if str(row.get('is_bookmarked')) == '1' else "✅ "
                st.markdown(f"**{status_icon}[{row.get('title', '未知')}]({row.get('source_url', '#')})**")
                
                # 副標題/導演
                if style_type == "movie":
                    st.caption(f"🎬 {str(row.get('creator', '未知導演'))[:30]}")
                else:
                    st.caption(f"🎵 {str(row.get('creator', '未知音樂家'))[:30]}")


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
        if st.toggle("🛠️ 啟用批量管理模式", key="media_edit_mode"):
            pass 
        else:
            st.session_state.selected_media = []
            st.session_state.show_delete_confirm = False

    st.caption("收納跨越文本之外的影視地圖、專輯聲響與社群分享卡片。")
    
    # 🌟 核心切換器：待播清單(1) vs 典藏庫(0)
    view_mode = st.radio("📂 選擇視圖區塊：", ["⏳ 待看/待播清單", "🏛️ 已完食/典藏庫"], horizontal=True, label_visibility="collapsed")
    current_view_state = 1 if "待看" in view_mode else 0

    # === 管理模式工具列 (動態按鈕版) ===
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
            c1, c2, c3 = st.columns([4, 3, 3])
            with c1:
                st.markdown(f"**批量管理** (目前已選: {len(st.session_state.selected_media)} 項)")
            with c2:
                # 動態改變按鈕邏輯與文字
                if current_view_state == 1:
                    if st.button("✅ 標記為已完食 (移至典藏)", use_container_width=True, disabled=len(st.session_state.selected_media)==0):
                        core_utils.batch_toggle_media_bookmark(st.session_state.selected_media, 0) # 0 = 典藏庫
                        st.session_state.selected_media = []
                        st.rerun()
                else:
                    if st.button("⏳ 退回待播清單", use_container_width=True, disabled=len(st.session_state.selected_media)==0):
                        core_utils.batch_toggle_media_bookmark(st.session_state.selected_media, 1) # 1 = 待播
                        st.session_state.selected_media = []
                        st.rerun()
            with c3:
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
            movie_input = st.text_input("輸入 IMDb 網址或 ID：", placeholder="例如貼上 IMDb 網址，或輸入 tt4003440", label_visibility="collapsed", key="movie_in_key")
        with col_m_btn:
            btn_text = "加入待播庫" if current_view_state == 1 else "直接加入典藏"
            if st.button(btn_text, use_container_width=True, type="primary", key="movie_btn_key"):
                if movie_input:
                    with st.spinner("正在呼叫 TMDB API 解鎖數據與導演..."):
                        m_data = core_utils.fetch_movie_data(movie_input)
                        if m_data:
                            m_data['is_bookmarked'] = current_view_state 
                            core_utils.insert_media_db(m_data) 
                            
                            success_msg = "待播清單" if current_view_state == 1 else "典藏庫"
                            st.success(f"🎬 已成功加入{success_msg}：{m_data['title']}")
                            st.rerun()
                        else:
                            st.error("❌ 抓取失敗，請確認網址或稍後再試。")
        st.divider()
            
        st.markdown(f"### 🍿 {'我的待播電影' if current_view_state == 1 else '電影典藏庫'}")
        movies = core_utils.fetch_media_by_broad_type("Movie", is_bookmarked=current_view_state)
        render_media_gallery(movies, tab_name="movie", style_type="movie", current_view_state=current_view_state)

    # ====================================================================
    # 🎵 分頁二：音樂與專輯
    # ====================================================================
    with tab_music:
        st.markdown("### 📥 引入音樂文獻")
        col_mu_in, col_mu_btn = st.columns([5, 1])
        with col_mu_in:
            music_input = st.text_input("輸入 Apple Music 網址或 ID：", placeholder="支援全區 Apple Music 網址", label_visibility="collapsed", key="music_in_key")
        with col_mu_btn:
            btn_text_mu = "加入待聽庫" if current_view_state == 1 else "直接加入典藏"
            if st.button(btn_text_mu, use_container_width=True, type="primary", key="music_btn_key"):
                if music_input:
                    with st.spinner("正在跨區輪詢 Apple Music API..."):
                        mu_data = core_utils.fetch_apple_music_data(music_input)
                        if mu_data:
                            mu_data['is_bookmarked'] = current_view_state
                            core_utils.insert_media_db(mu_data)
                            
                            success_msg = "待聽清單" if current_view_state == 1 else "典藏庫"
                            st.success(f"🎵 已成功加入{success_msg}：{mu_data['title']}")
                            st.rerun()
                        else:
                            st.error("❌ 抓取失敗，找不到此專輯。")
        st.divider()
            
        st.markdown(f"### 🎧 {'我的待聽專輯' if current_view_state == 1 else '音樂典藏庫'}")
        music_list = core_utils.fetch_media_by_broad_type("Music", is_bookmarked=current_view_state)
        render_media_gallery(music_list, tab_name="music", style_type="music", current_view_state=current_view_state)

    # ====================================================================
    # 🌐 分頁三：網路資源分享卡
    # ====================================================================
    with tab_resource:
        st.markdown("### 🌐 快收網路社群與卡片連結")
        st.caption("此分頁適合備存 Twitter、Facebook 貼文。此區塊不分待播/典藏。")
        
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
            # 🌟 套用全域分頁引擎
            page_data, total_pages, current_page = ui_components.paginate_data(df, per_page=20, session_key="mono_page")
            
            for _, row in page_data.iterrows():
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
            ui_components.render_pagination_ui(total_pages, current_page, "mono_page")
