import streamlit as st
import core_utils
import pandas as pd

def render_page():
    st.header("🎬 影音與網路資源館 (Media Vault)")
    st.caption("收納跨越文本之外的影視地圖、專輯聲響與社群分享卡片。")
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
            if st.button("加入電影庫", use_container_width=True, type="primary", key="movie_btn_key"):
                if movie_input:
                    with st.spinner("正在呼叫 TMDB API 解鎖數據..."):
                        m_data = core_utils.fetch_media_by_url(movie_input)
                        if m_data:
                            core_utils.insert_media_db(m_data)
                            st.success("🎬 電影已成功加入歸檔！")
                            st.rerun()
                else: st.warning("請先輸入網址或 ID。")
                
        st.markdown("---")
        
        movies = core_utils.fetch_media_by_broad_type("Movie")
        if not movies:
            st.info("📦 目前電影館空空如也。")
        else:
            for i in range(0, len(movies), 5):
                chunk = movies[i:i+5]
                cols = st.columns(5)
                for j, item in enumerate(chunk):
                    with cols[j]:
                        with st.container():
                            cover_data = item.get('cover_image')
                            if cover_data:
                                img_src = f"data:image/jpeg;base64,{cover_data}" if not str(cover_data).startswith("http") else cover_data
                                st.markdown(f'<img src="{img_src}" style="width:100%; aspect-ratio: 2/3; border-radius:6px; box-shadow: 0 4px 6px rgba(0,0,0,0.15); margin-bottom:8px; object-fit: cover;">', unsafe_allow_html=True)
                            else:
                                st.markdown('<div style="width:100%; aspect-ratio: 2/3; background-color:#262626; border-radius:6px; margin-bottom:8px; display:flex; align-items:center; justify-content:center; color:#525252; font-size:12px;">🎬 No Cover</div>', unsafe_allow_html=True)
                            
                            st.markdown(f"**{item.get('title', '未知標題')}**")
                            st.caption(f"👤 {item.get('creator', '未知來源')}")
                            
                            with st.popover("⚙️ 管理", use_container_width=True):
                                st.caption(item.get('summary', '無簡介'))
                                st.markdown(f"[🔗 前往來源網頁]({item.get('source_url', '#')})")
                                if st.button("🗑️ 確定抹除", key=f"del_m_{item.get('id')}", type="primary", use_container_width=True):
                                    core_utils.delete_media_db(item.get('id'))
                                    st.rerun()
                        st.markdown("<br>", unsafe_allow_html=True)

    # ====================================================================
    # 🎵 分頁二：音樂與專輯
    # ====================================================================
    with tab_music:
        st.markdown("### 📥 引入音樂檔案")
        col_mu_in, col_mu_btn = st.columns([5, 1])
        with col_mu_in:
            music_input = st.text_input("輸入 Apple Music ID 或網址：", placeholder="例如直接輸入純數字: 1530598395", label_visibility="collapsed", key="music_in_key")
        with col_mu_btn:
            if st.button("加入音樂庫", use_container_width=True, type="primary", key="music_btn_key"):
                if music_input:
                    with st.spinner("智慧輪詢全球 Apple Music 伺服器中..."):
                        mu_data = core_utils.fetch_media_by_url(music_input, force_type="Music")
                        if mu_data:
                            core_utils.insert_media_db(mu_data)
                            st.success("🎵 音樂專輯已成功入庫！")
                            st.rerun()
                else: st.warning("請先輸入音樂 ID 或網址。")
                
        st.markdown("---")
        
        music_list = core_utils.fetch_media_by_broad_type("Music")
        if not music_list:
            st.info("📦 目前音樂館尚無收藏。")
        else:
            for i in range(0, len(music_list), 5):
                chunk = music_list[i:i+5]
                cols = st.columns(5)
                for j, item in enumerate(chunk):
                    with cols[j]:
                        with st.container():
                            cover_data = item.get('cover_image')
                            if cover_data:
                                img_src = f"data:image/jpeg;base64,{cover_data}" if not str(cover_data).startswith("http") else cover_data
                                st.markdown(f'<img src="{img_src}" style="width:100%; aspect-ratio: 1/1; border-radius:6px; box-shadow: 0 4px 6px rgba(0,0,0,0.15); margin-bottom:8px; object-fit: cover;">', unsafe_allow_html=True)
                            else:
                                st.markdown('<div style="width:100%; aspect-ratio: 1/1; background-color:#262626; border-radius:6px; margin-bottom:8px; display:flex; align-items:center; justify-content:center; color:#525252; font-size:12px;">🎵 No Cover</div>', unsafe_allow_html=True)
                            
                            st.markdown(f"**{item.get('title', '未知標題')}**")
                            st.caption(f"🎤 {item.get('creator', '未知歌手')} | {item.get('media_type', '音樂')}")
                            
                            with st.popover("⚙️ 管理", use_container_width=True):
                                st.write(item.get('summary', ''))
                                st.markdown(f"[🔗 前往 Apple Music]({item.get('source_url', '#')})")
                                if st.button("🗑️ 確定抹除", key=f"del_mu_{item.get('id')}", type="primary", use_container_width=True):
                                    core_utils.delete_media_db(item.get('id'))
                                    st.rerun()
                        st.markdown("<br>", unsafe_allow_html=True)

    # ====================================================================
    # 🌐 分頁三：網路資源分享卡
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
                        # 🌟 修正1：精準對齊您的 add_custom_resource 參數 (folder, url)
                        if core_utils.add_custom_resource("media_vault", res_url):
                            st.success("🌐 分享卡片已加入備存清單！")
                            st.rerun()
                else: st.warning("請輸入完整的 http 網址。")
                
        st.markdown("---")
        
        # 🌟 修正2：精準對齊您的 fetch_custom_resources 參數 (folder) 並且處理 Pandas DataFrame
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
                            new_title = st.text_input("修改卡片名稱:", value=row.get('title', ''), key=f"edit_t_{row['id']}")
                            current_comment = row.get('comment', '') if pd.notna(row.get('comment')) else ""
                            new_comment = st.text_area("添加自訂備註/筆記:", value=current_comment, key=f"edit_c_{row['id']}")
                            
                            # 🌟 修正3：精準對齊您的 update_custom_resource 參數 (id, title, comment)
                            if st.button("💾 保存修改", key=f"save_c_{row['id']}", use_container_width=True):
                                core_utils.update_custom_resource(row['id'], new_title, new_comment)
                                st.rerun()
                                
                            st.divider()
                            # 🌟 修正4：精準對齊您的 delete_custom_resource 參數 (id)
                            if st.button("🗑️ 徹底刪除", key=f"del_card_{row['id']}", type="primary", use_container_width=True):
                                core_utils.delete_custom_resource(row['id'])
                                st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)
