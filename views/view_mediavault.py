import streamlit as st
import core_utils
import pandas as pd

def render_page():
    st.header("🎬 影音與網路資源館 (Media Vault)")
    st.caption("收納跨越文本之外的影視地圖、專輯聲響與社群分享卡片。")
    st.markdown("---")
    
    tab_movie, tab_music, tab_resource = st.tabs(["🎬 電影與影集", "🎵 音樂與專輯", "🌐 網路資源分享卡"])
    
    # 取得資料庫內容 (修正 TypeError：不寫 module=)
    # 假設這會回傳一個 Pandas DataFrame
    df_vault = core_utils.fetch_custom_resources("media_vault")
    has_data = isinstance(df_vault, pd.DataFrame) and not df_vault.empty

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
                    with st.spinner("正在呼叫 API 解鎖數據..."):
                        m_data = core_utils.fetch_movie_data(movie_input)
                        if m_data:
                            # 確保 insert_media_db 接收這個 6 鍵字典
                            core_utils.insert_media_db(m_data) 
                            st.success(f"🎬 已成功加入：{m_data['title']}")
                            st.rerun()
                        else:
                            st.error("❌ 抓取失敗，請確認網址或稍後再試。")
        
        st.divider()
        st.markdown("### 🍿 我的電影庫")
        if has_data:
            # 篩選電影資料
            df_movies = df_vault[df_vault['media_type'] == "🎬 電影"].reset_index(drop=True)
            if not df_movies.empty:
                # 🛡️ 完美的 5 欄網格排版 (杜絕 IndexError)
                cols = st.columns(5)
                for i, (index, row) in enumerate(df_movies.iterrows()):
                    col_idx = i % 5  # 永遠在 0~4 之間循環
                    with cols[col_idx]:
                        with st.container(border=True):
                            # 防護：檢查 base64 圖片是否存在
                            cover = row.get('cover_image')
                            if pd.notna(cover) and str(cover).startswith('data:image'):
                                st.markdown(f'<img src="{cover}" width="100%" style="border-radius:8px;"/>', unsafe_allow_html=True)
                            else:
                                st.info("無海報")
                            
                            st.markdown(f"**[{row.get('title', '未知')}]({row.get('source_url', '#')})**")
                            st.caption(str(row.get('summary', ''))[:50] + "...")
            else:
                st.info("目前尚無電影收藏。")

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
        if has_data:
            df_music = df_vault[df_vault['media_type'] == "🎵 音樂"].reset_index(drop=True)
            if not df_music.empty:
                # 🛡️ 同樣安全的 5 欄網格排版
                cols = st.columns(5)
                for i, (index, row) in enumerate(df_music.iterrows()):
                    col_idx = i % 5 
                    with cols[col_idx]:
                        with st.container(border=True):
                            cover = row.get('cover_image')
                            if pd.notna(cover) and str(cover).startswith('data:image'):
                                st.markdown(f'<img src="{cover}" width="100%" style="border-radius:50%; box-shadow: 2px 2px 10px rgba(0,0,0,0.5);"/>', unsafe_allow_html=True)
                            else:
                                st.info("無封面")
                            
                            st.markdown(f"**[{row.get('title', '未知')}]({row.get('source_url', '#')})**")
                            st.caption(row.get('creator', '未知創作者'))
            else:
                st.info("目前尚無音樂收藏。")

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
                            new_title = st.text_input("修改卡片名稱:", value=row.get('title', ''), key=f"edit_t_{row['id']}")
                            current_comment = row.get('comment', '') if pd.notna(row.get('comment')) else ""
                            new_comment = st.text_area("添加自訂備註/筆記:", value=current_comment, key=f"edit_c_{row['id']}")
                            
                            if st.button("💾 保存修改", key=f"save_c_{row['id']}", use_container_width=True):
                                core_utils.update_custom_resource(row['id'], new_title, new_comment)
                                st.rerun()
                                
                            st.divider()
                            if st.button("🗑️ 徹底刪除", key=f"del_card_{row['id']}", type="primary", use_container_width=True):
                                core_utils.delete_custom_resource(row['id'])
                                st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)
