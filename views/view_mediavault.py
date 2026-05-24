import streamlit as st
import core_utils

def render_page():
    st.header("🎬 影音館 (Media Vault)")
    
    # 頂部：獨立的智慧輸入區塊
    with st.container():
        st.markdown("### 📥 加入新收藏")
        col_input, col_btn = st.columns([5, 1])
        with col_input:
            # 🌟 更新了提示文字，告知使用者可以直接輸入 ASIN 碼
            media_url = st.text_input(
                "輸入網址", 
                placeholder="貼上 IMDb/豆瓣/Amazon網址，或直接輸入 ASIN 碼 / IMDb ID (tt...)", 
                label_visibility="collapsed"
            )
        with col_btn:
            if st.button("解析並加入", use_container_width=True, type="primary"):
                if media_url:
                    with st.spinner("正在解析媒體資訊..."):
                        media_data = core_utils.fetch_media_by_url(media_url)
                        if media_data:
                            core_utils.insert_media_db(media_data)
                            st.success("✅ 成功加入影音館！")
                            st.rerun() 
                        else:
                            st.error("❌ 解析失敗，請確認網址或 ASIN 是否正確。")
                else:
                    st.warning("請先輸入網址或代碼。")
                    
    st.markdown("---")
    
    # 底部：視覺化網格展示區
    media_list = core_utils.fetch_all_media()
    
    if not media_list:
        st.info("📦 影音館目前還是空的，試著輸入一個 Amazon ASIN 碼吧！")
        return

    # 使用 5 欄網格排列
    cols_per_row = 5
    for i in range(0, len(media_list), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            if i + j < len(media_list):
                item = media_list[i + j]
                with col:
                    # 渲染封面圖 (支援 Base64 防盜鏈)
                    if item.get('cover_image'):
                        img_src = f"data:image/jpeg;base64,{item['cover_image']}" if not str(item['cover_image']).startswith("http") else item['cover_image']
                        st.markdown(f'<img src="{img_src}" style="width:100%; aspect-ratio: 2/3; border-radius:8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom:10px; object-fit: cover;">', unsafe_allow_html=True)
                    else:
                        # 找不到封面的預設灰底圖
                        st.markdown(f'<div style="width:100%; aspect-ratio: 2/3; background-color:#333; border-radius:8px; margin-bottom:10px;"></div>', unsafe_allow_html=True)
                    
                    st.markdown(f"**{item['title']}**")
                    st.caption(f"{item['type']} | [🔗來源]({item['source_url']})")
