import streamlit as st
import core_utils

def render_page():
    st.header("🎬 影音館 (Media Vault)")
    
    # 頂部：獨立的網址輸入區塊
    with st.container():
        st.markdown("### 📥 加入新收藏")
        col_input, col_btn = st.columns([5, 1])
        with col_input:
            media_url = st.text_input("貼上 IMDb, 豆瓣電影, 或 Amazon 音樂網址：", placeholder="https://...", label_visibility="collapsed")
        with col_btn:
            if st.button("解析並加入", use_container_width=True, type="primary"):
                if media_url:
                    with st.spinner("正在解析媒體資訊..."):
                        media_data = core_utils.fetch_media_by_url(media_url)
                        if media_data:
                            core_utils.insert_media_db(media_data)
                            st.success("✅ 成功加入影音館！")
                            st.rerun() # 重新整理畫面顯示新卡片
                else:
                    st.warning("請先輸入網址。")
                    
    st.markdown("---")
    
    # 底部：視覺化網格展示區
    media_list = core_utils.fetch_all_media()
    
    # 使用 5 欄網格排列
    cols_per_row = 5
    for i in range(0, len(media_list), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            if i + j < len(media_list):
                item = media_list[i + j]
                with col:
                    # 渲染封面圖 (支援 Base64)
                    if item['cover_image']:
                        st.markdown(f'<img src="{item["cover_image"]}" style="width:100%; border-radius:8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom:10px;">', unsafe_allow_html=True)
                    st.markdown(f"**{item['title']}**")
                    st.caption(f"{item['creator']} | {item['media_type']}")
