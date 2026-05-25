import streamlit as st
import core_utils

def render_page():
    st.header("🎬 影音館 (測試版)")
    
    # 輸入區
    url = st.text_input("輸入網址或 ID:")
    if st.button("加入"):
        # 這裡我們手動模擬一個資料，先不要爬蟲，看能不能寫入顯示
        test_data = {
            'media_type': '測試', 'title': '測試標題', 'creator': '測試者', 
            'cover_image': 'https://via.placeholder.com/150', 'source_url': url
        }
        core_utils.insert_media_db(test_data)
        st.rerun()

    # 展示區
    data = core_utils.fetch_all_media()
    for item in data:
        st.divider()
        st.write(f"### {item.get('title')}")
        st.write(f"創作者: {item.get('creator')}")
        st.image(item.get('cover_image'))
