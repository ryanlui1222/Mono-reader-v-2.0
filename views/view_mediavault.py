import streamlit as st
import core_utils
import pandas as pd
from views import ui_components  # 🌟 引入全域元件

def render_media_gallery(media_list, tab_name, style_type="movie", current_view_state=1):
    """通用的畫廊渲染器：純粹負責排版與呼叫全域元件"""
    if not media_list:
        st.info("📦 此清單目前尚無收藏。")
        return
        
    page_key = f"{tab_name}_{current_view_state}_page"
    
    # 套用全域分頁引擎
    page_items, total_pages, current_page = ui_components.paginate_data(media_list, per_page=20, session_key=page_key)
    
    cols = st.columns(5)
    for i, row in enumerate(page_items):
        col_idx = i % 5
        with cols[col_idx]:
            with st.container(border=True):
                # 封面渲染 (保留音樂特有圓角)
                cover = row.get('cover_image')
                if cover and str(cover).startswith('data:image'):
                    if style_type == "music":
                        st.markdown(f'<img src="{cover}" width="100%" style="border-radius:50%; box-shadow: 2px 2px 10px rgba(0,0,0,0.5); margin-bottom:10px;"/>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<img src="{cover}" width="100%" style="border-radius:8px; margin-bottom:10px;"/>', unsafe_allow_html=True)
                else:
                    st.info("無圖片")
                
                # 標題與狀態符號
                status_icon = "⏳ " if str(row.get('is_bookmarked')) == '1' else "✅ "
                st.markdown(f"**{status_icon}[{row.get('title', '未知')}]({row.get('source_url', '#')})**")
                
                # 副標題/導演
                if style_type == "movie":
                    st.caption(f"🎬 {str(row.get('creator', '未知導演'))[:30]}")
                else:
                    st.caption(f"🎵 {str(row.get('creator', '未知音樂家'))[:30]}")
                
                # 🌟 【植入點 1】為每張卡片底部加入智慧管理按鈕
                ui_components.render_smart_popover(row, table_name="media_vault")
                    
    ui_components.render_pagination_ui(total_pages, current_page, page_key)


def render_page():
    # 🌟 頁面標題與「試算表管理」全域開關
    col_h1, col_h2 = st.columns([7, 3])
    with col_h1:
        st.header("🎬 影音與網路資源館 (Media Vault)")
    with col_h2:
        st.write("") 
        is_edit_mode = st.toggle("🛠️ 進入試算表管理模式", key="media_edit_mode")

    st.caption("收納跨越文本之外的影視地圖、專輯聲響與社群分享卡片。")
    
    view_mode = st.radio("📂 選擇視圖區塊：", ["⏳ 待看/待播清單", "🏛️ 已完食/典藏庫"], horizontal=True, label_visibility="collapsed")
    current_view_state = 1 if "待看" in view_mode else 0

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
        
        # 🌟 【植入點 2】視圖分流：卡片 vs 試算表
        if is_edit_mode:
            if movies:
                df_movies = pd.DataFrame(movies) # 轉成 DataFrame 給編輯器吃
                ui_components.render_batch_editor(df_movies, table_name="media_vault", key_prefix="movie")
            else:
                st.info("目前無資料可供編輯。")
        else:
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
        
        # 🌟 【植入點 3】視圖分流：卡片 vs 試算表
        if is_edit_mode:
            if music_list:
                df_music = pd.DataFrame(music_list)
                ui_components.render_batch_editor(df_music, table_name="media_vault", key_prefix="music")
            else:
                st.info("目前無資料可供編輯。")
        else:
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
        
        # 🌟 【植入點 4】視圖分流：資源卡列表 vs 試算表
        if is_edit_mode:
            if df_res is not None and not df_res.empty:
                ui_components.render_batch_editor(df_res, table_name="custom_resources", key_prefix="resource")
            else:
                st.info("目前無資料可供編輯。")
        else:
            if df_res is None or df_res.empty:
                st.info("📦 目前還沒有儲存任何社群資源卡片。")
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
                            # 🌟 【植入點 5】取代原本落落長的修改按鈕，一行呼叫完成！
                            ui_components.render_smart_popover(row, table_name="custom_resources")
                            
                    st.markdown("<br>", unsafe_allow_html=True)
                ui_components.render_pagination_ui(total_pages, current_page, "media_res_page")
