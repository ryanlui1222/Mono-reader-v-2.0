import streamlit as st
import core_utils

def render_page():
    st.header("🎬 影音與網路資源館 (Media Vault)")
    st.caption("收納跨越文本之外的影視地圖、專輯聲響與社群分享卡片。")
    st.markdown("---")
    
    tab_movie, tab_music, tab_resource = st.tabs(["🎬 電影與影集", "🎵 音樂與專輯", "🌐 網路資源分享卡"])
    
    # ====================================================================
    # 分頁一：電影與影集
    # ====================================================================
    with tab_movie:
        st.markdown("### 📥 引入電影文獻")
        col_m_in, col_m_btn = st.columns([5, 1])
        with col_m_in:
            movie_input = st.text_input("輸入網址或代碼：", placeholder="貼上 IMDb 網址、豆瓣電影網址，或直接輸入 IMDb ID (例如: tt4003440)", label_visibility="collapsed", key="movie_in_key")
        with col_m_btn:
            if st.button("加入電影庫", use_container_width=True, type="primary", key="movie_btn_key"):
                if movie_input:
                    with st.spinner("正在解鎖影視元數據..."):
                        m_data = core_utils.fetch_media_by_url(movie_input)
                        if m_data:
                            core_utils.insert_media_db(m_data)
                            st.success("🎬 電影已成功加入歸檔！")
                            st.rerun()
                else: st.warning("請先輸入電影網址或 ID。")
                
        st.markdown("---")
        
        movies = core_utils.fetch_media_by_broad_type("Movie")
        if not movies:
            st.info("📦 目前電影館空空如也。")
        else:
            cols_per_row = 5
            for i in range(0, len(movies), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    if i + j < len(movies):
                        item = movies[i + j]
                        with col:
                            # 🌟 安全讀取 cover_image 欄位
                            cover_data = item.get('cover_image')
                            if cover_data:
                                img_src = f"data:image/jpeg;base64,{cover_data}" if not str(cover_data).startswith("http") else cover_data
                                st.markdown(f'<img src="{img_src}" style="width:100%; aspect-ratio: 2/3; border-radius:6px; box-shadow: 0 4px 6px rgba(0,0,0,0.15); margin-bottom:8px; object-fit: cover;">', unsafe_allow_html=True)
                            else:
                                st.markdown('<div style="width:100%; aspect-ratio: 2/3; background-color:#262626; border-radius:6px; margin-bottom:8px; display:flex; align-items:center; justify-content:center; color:#525252; font-size:12px;">🎬 No Cover</div>', unsafe_allow_html=True)
                            
                            # 🌟 安全防呆讀取 .get() 
                            st.markdown(f"**{item.get('title', '未知標題')}**")
                            st.caption(f"👤 {item.get('creator', '未知來源')}")
                            
                            with st.popover("⚙️ 管理", use_container_width=True):
                                st.caption(item.get('summary', '無簡介'))
                                st.markdown(f"[🔗 前往來源網頁]({item.get('source_url', '#')})")
                                if st.button("🗑️ 確定抹除", key=f"del_m_{item.get('id')}", type="primary", use_container_width=True):
                                    core_utils.delete_media_db(item.get('id'))
                                    st.rerun()

    # ====================================================================
    # 分頁二：音樂與專輯
    # ====================================================================
    with tab_music:
        st.markdown("### 📥 引入音樂檔案")
        col_mu_in, col_mu_btn = st.columns([5, 1])
        with col_mu_in:
            music_input = st.text_input("輸入 Apple Music ID 或網址：", placeholder="例如直接輸入純數字: 1530598395 (或是整串 music.apple.com 網址)", label_visibility="collapsed", key="music_in_key")
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
            cols_per_row = 5
            for i in range(0, len(music_list), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    if i + j < len(music_list):
                        item = music_list[i + j]
                        with col:
                            cover_data = item.get('cover_image')
                            if cover_data:
                                img_src = f"data:image/jpeg;base64,{cover_data}" if not str(cover_data).startswith("http") else cover_data
                                st.markdown(f'<img src="{img_src}" style="width:100%; aspect-ratio: 1/1; border-radius:6px; box-shadow: 0 4px 6px rgba(0,0,0,0.15); margin-bottom:8px; object-fit: cover;">', unsafe_allow_html=True)
                            else:
                                st.markdown('<div style="width:100%; aspect-ratio: 1/1; background-color:#262626; border-radius:6px; margin-bottom:8px; display:flex; align-items:center; justify-content:center; color:#525252; font-size:12px;">🎵 No Cover</div>', unsafe_allow_html=True)
                            
                            st.markdown(f"**{item.get('title', '未知標題')}**")
                            # 🌟 將原先出錯的 item['type'] 修正為符合資料庫欄位名稱的 item.get('media_type')
                            st.caption(f"🎤 {item.get('creator', '未知歌手')} | {item.get('media_type', '音樂')}")
                            
                            with st.popover("⚙️ 管理", use_container_width=True):
                                st.write(item.get('summary', ''))
                                st.markdown(f"[🔗 前往 Apple Music]({item.get('source_url', '#')})")
                                if st.button("🗑️ 確定抹除", key=f"del_mu_{item.get('id')}", type="primary", use_container_width=True):
                                    core_utils.delete_media_db(item.get('id'))
                                    st.rerun()

    # ====================================================================
    # 分頁三：網路資源分享卡
    # ====================================================================
    with tab_resource:
        st.markdown("### 🌐 快收網路社群與卡片連結")
        st.caption("此分頁不進行複雜的影視音爬蟲，僅擷取網站的分享元標籤 (OG Card)，適合備存 Twitter、Facebook 貼文。")
        
        col_res_in, col_res_btn = st.columns([5, 1])
        with col_res_in:
            res_url = st.text_input("貼上社群或外部資源網址：", placeholder="https://x.com/... 或 https://facebook.com/...", label_visibility="collapsed", key="res_in_key")
        with col_res_btn:
            if st.button("快存卡片", use_container_width=True, type="primary", key="res_btn_key"):
                if res_url.startswith("http"):
                    with st.spinner("正在快取分享卡片資訊..."):
                        if core_utils.add_custom_resource(res_url, module='media_vault'):
                            st.success("🌐 分享卡片已加入備存清單！")
                            st.rerun()
                else: st.warning("請輸入完整的 http 網址。")
                
        st.markdown("---")
        
        res_cards = core_utils.fetch_custom_resources(module='media_vault')
        if not res_cards:
            st.info("📦 目前還沒有儲存任何社群資源卡片。")
        else:
            for card in res_cards:
                with st.container():
                    col_card_meta, col_card_opt = st.columns([5, 1])
                    with col_card_meta:
                        st.markdown(f"#### [{card.get('title', '無標題')}]({card.get('url', '#')})")
                        st.caption(f"🔗 來源網址: {card.get('url', '#')}")
                        if card.get('comment'):
                            st.info(card['comment'])
                            
                    with col_card_opt:
                        with st.popover("⚙️ 管理卡片", use_container_width=True):
                            new_title = st.text_input("修改卡片名稱:", value=card.get('title', ''), key=f"edit_t_{card.get('id')}")
                            if new_title != card.get('title', ''):
                                core_utils.update_custom_resource_title(card.get('id'), new_title)
                                st.rerun()
                                
                            new_comment = st.text_area("添加自訂備註/筆記:", value=card.get('comment', ''), key=f"edit_c_{card.get('id')}")
                            if st.button("💾 保存備註", key=f"save_c_{card.get('id')}", use_container_width=True):
                                core_utils.update_custom_resource_comment(card.get('id'), new_comment)
                                st.rerun()
                                
                            st.divider()
                            if st.button("🗑️ 徹底刪除", key=f"del_card_{card.get('id')}", type="primary", use_container_width=True):
                                core_utils.delete_custom_resource(card.get('id'))
                                st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)
