import streamlit as st
import core_utils
import pandas as pd
from views import ui_components

def render_media_gallery(df_media, tab_name, style_type="movie", current_view_state=1):
    if df_media.empty:
        st.info("📦 此清單目前尚無相符收藏。")
        return
        
    page_key = f"{tab_name}_{current_view_state}_page"
    page_items, total_pages, current_page = ui_components.paginate_data(df_media, per_page=20, session_key=page_key)
    
    cols = st.columns(5)
    for i, row in page_items.reset_index(drop=True).iterrows():
        col_idx = i % 5
        with cols[col_idx]:
            with st.container(border=True):
                cover = row.get('cover_image')
                if cover and str(cover).startswith('data:image'):
                    if style_type == "music":
                        st.markdown(f'<img src="{cover}" width="100%" style="border-radius:50%; box-shadow: 2px 2px 10px rgba(0,0,0,0.5); margin-bottom:10px;"/>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<img src="{cover}" width="100%" style="border-radius:8px; margin-bottom:10px;"/>', unsafe_allow_html=True)
                else:
                    st.info("無圖片")
                
                status_icon = "⏳ " if str(row.get('is_bookmarked')) == '1' else "✅ "
                st.markdown(f"**{status_icon}[{row.get('title', '未知')}]({row.get('source_url', '#')})**")
                
                if style_type == "movie": st.caption(f"🎬 {str(row.get('creator', '未知導演'))[:30]}")
                else: st.caption(f"🎵 {str(row.get('creator', '未知音樂家'))[:30]}")
                
                ui_components.render_smart_popover(row, table_name="media_vault")
                    
    ui_components.render_pagination_ui(total_pages, current_page, page_key)


def render_page():
    with st.sidebar:
        st.subheader("🔍 當前分頁搜尋")
        media_local_search = st.text_input("輸入關鍵字", placeholder="過濾當前清單...", label_visibility="collapsed")
        st.markdown("---")
        # 🌟 統一導航模式
        media_view_mode = st.radio("瀏覽模式", ["⏳ 待播 / 待看清單", "🏛️ 典藏庫 / 已完食", "🔍 搜尋中心"])
        current_view_state = 1 if "待播" in media_view_mode else 0

    col_h1, col_h2 = st.columns([7, 3])
    with col_h1: st.header("🎬 影音與網路資源館 (Media Vault)")
    with col_h2:
        st.write("") 
        is_edit_mode = st.toggle("🛠️ 進入試算表管理模式", key="media_edit_mode")
    
    st.markdown("---")

    # ==========================================
    # 🌟 獨立的搜尋中心分頁
    # ==========================================
    if media_view_mode == "🔍 搜尋中心":
        st.subheader("🔍 全域搜尋中心")
        global_q = st.text_input("跨板塊搜尋：", placeholder="搜尋所有電影、音樂與資源卡片...", key="media_global")
        st.markdown("---")
        
        if not global_q:
            st.info("👈 請在上方輸入關鍵字，系統將為您檢索所有影音與社群分享卡片。")
        else:
            # 搜尋待看區
            movies_1 = core_utils.fetch_media_by_broad_type("Movie", is_bookmarked=1, search_query=global_q)
            music_1 = core_utils.fetch_media_by_broad_type("Music", is_bookmarked=1, search_query=global_q)
            # 搜尋已看區
            movies_0 = core_utils.fetch_media_by_broad_type("Movie", is_bookmarked=0, search_query=global_q)
            music_0 = core_utils.fetch_media_by_broad_type("Music", is_bookmarked=0, search_query=global_q)
            
            all_media = movies_1 + music_1 + movies_0 + music_0
            if all_media:
                st.markdown(f"#### 🎬 影視與音樂 ({len(all_media)} 筆)")
                for item in all_media:
                    loc = "待播清單" if str(item.get('is_bookmarked')) == '1' else "典藏庫"
                    st.markdown(f"- **[{item.get('title', '未知')}]({item.get('source_url', '#')})** ｜ 👤 {item.get('creator', '')} ｜ 📍 位於：`{loc}`")
                st.write("")

            df_res = core_utils.fetch_custom_resources("media_vault", search_query=global_q)
            if not df_res.empty:
                st.markdown(f"#### 🌐 社群資源卡片 ({len(df_res)} 筆)")
                for _, row in df_res.iterrows():
                    st.markdown(f"- **[{row.get('title', '未命名')}]({row.get('url', '#')})** ｜ 📍 位於：`網路資源分享卡`")

            if not all_media and df_res.empty:
                st.warning(f"在 Media Vault 模組中，找不到包含「{global_q}」的資料。")

    # ==========================================
    # 一般內容分頁
    # ==========================================
    else:
        tab_movie, tab_music, tab_resource = st.tabs(["🎬 電影與影集", "🎵 音樂與專輯", "🌐 網路資源分享卡"])

        with tab_movie:
            with st.expander("📥 引入電影文獻", expanded=False):
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
                                    st.success(f"🎬 已成功加入：{m_data['title']}"); st.rerun()
                                else: st.error("❌ 抓取失敗，請確認網址或稍後再試。")
                
            st.markdown(f"### 🍿 {'我的待播電影' if current_view_state == 1 else '電影典藏庫'}")

            # 🌟 傳入局域搜尋
            movies = core_utils.fetch_media_by_broad_type("Movie", is_bookmarked=current_view_state, search_query=media_local_search)
            df_movies = pd.DataFrame(movies) if movies else pd.DataFrame()
            df_movies = ui_components.apply_smart_sort(df_movies, table_name="media_vault", context_key="edit_movie")

            if is_edit_mode:
                if df_movies.empty: st.info("目前無資料可供編輯。")
                else: ui_components.render_batch_editor(df_movies, table_name="media_vault", key_prefix="movie")
            else:
                render_media_gallery(df_movies, tab_name="movie", style_type="movie", current_view_state=current_view_state)

        with tab_music:
            with st.expander("📥 引入音樂文獻", expanded=False):
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
                                    st.success(f"🎵 已成功加入：{mu_data['title']}"); st.rerun()
                                else: st.error("❌ 抓取失敗，找不到此專輯。")
                
            st.markdown(f"### 🎧 {'我的待聽專輯' if current_view_state == 1 else '音樂典藏庫'}")

            # 🌟 傳入局域搜尋
            music_list = core_utils.fetch_media_by_broad_type("Music", is_bookmarked=current_view_state, search_query=media_local_search)
            df_music = pd.DataFrame(music_list) if music_list else pd.DataFrame()
            df_music = ui_components.apply_smart_sort(df_music, table_name="media_vault", context_key="edit_music")

            if is_edit_mode:
                if df_music.empty: st.info("目前無資料可供編輯。")
                else: ui_components.render_batch_editor(df_music, table_name="media_vault", key_prefix="music")
            else:
                render_media_gallery(df_music, tab_name="music", style_type="music", current_view_state=current_view_state)

        with tab_resource:
            with st.expander("🌐 快收網路社群與卡片連結", expanded=False):
                col_res_in, col_res_btn = st.columns([5, 1])
                with col_res_in:
                    res_url = st.text_input("貼上社群或外部資源網址：", placeholder="https://x.com/...", label_visibility="collapsed", key="res_in_key")
                with col_res_btn:
                    if st.button("快存卡片", use_container_width=True, type="primary", key="res_btn_key"):
                        if res_url.startswith("http"):
                            with st.spinner("正在快取分享卡片資訊..."):
                                if core_utils.add_custom_resource("media_vault", res_url):
                                    st.success("🌐 分享卡片已加入備存清單！"); st.rerun()
                        else: st.warning("請輸入完整的 http 網址。")
            
            st.markdown("### 🌐 網路分享卡片陳列室")

            # 🌟 傳入局域搜尋
            df_res = core_utils.fetch_custom_resources("media_vault", search_query=media_local_search)
            df_res = ui_components.apply_smart_sort(df_res, table_name="custom_resources", context_key="media_res")
            
            if is_edit_mode:
                if df_res.empty: st.info("目前無資料可供編輯。")
                else: ui_components.render_batch_editor(df_res, table_name="custom_resources", key_prefix="resource")
            else:
                if df_res.empty: st.info("📦 目前沒有相符的社群資源卡片。")
                else:
                    page_data, total_pages, current_page = ui_components.paginate_data(df_res, per_page=20, session_key="media_res_page")
                    for _, row in page_data.iterrows():
                        with st.container():
                            col_card_meta, col_card_opt = st.columns([5, 1])
                            with col_card_meta:
                                st.markdown(f"#### [{row.get('title', '無標題')}]({row.get('url', '#')})")
                                st.caption(f"🔗 來源網址: {row.get('url', '#')}")
                                if pd.notna(row.get('comment')) and str(row.get('comment')).strip():
                                    st.info(row['comment'])
                                    
                            with col_card_opt:
                                ui_components.render_smart_popover(row, table_name="custom_resources")
                                
                        st.markdown("<br>", unsafe_allow_html=True)
                    ui_components.render_pagination_ui(total_pages, current_page, "media_res_page")
