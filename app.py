import streamlit as st
from views import view_monoreader, view_biblioapp

# ==========================================
# 1. 介面基礎設定 & 全域 CSS 注入
# ==========================================
st.set_page_config(page_title="Monoreader Cloud", page_icon="📚", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.memoof-cover img {
    width: 100%; aspect-ratio: 2 / 3; object-fit: contain; 
    background-color: #1E1E1E; border-radius: 4px;
    box-shadow: 2px 4px 8px rgba(0,0,0,0.3); transition: transform 0.2s ease-in-out;
}
.memoof-cover img:hover { transform: scale(1.03); }
.memoof-meta { margin-top: 10px; text-align: left; }
.memoof-title {
    font-size: 14px; font-weight: bold; line-height: 1.3; color: #E2E8F0; 
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; 
    overflow: hidden; text-overflow: ellipsis; height: 36px;
}
.memoof-author { font-size: 12px; color: #94A3B8; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stButton button { margin-top: 5px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 側邊欄總開關 (Router)
# ==========================================
with st.sidebar:
    st.title("☁️ Monoreader Cloud")
    app_mode = st.radio("切換平台模組", ["📚 Monoreader", "🎓 Biblioapp"], index=0, label_visibility="collapsed")
    st.divider()

# ==========================================
# 3. 模組渲染導流
# ==========================================
if app_mode == "📚 Monoreader":
    view_monoreader.render_page()
elif app_mode == "🎓 Biblioapp":
    view_biblioapp.render_page()

st.sidebar.markdown("---")
st.sidebar.caption("Monoreader Cloud v4.1 (Modular Architecture Edition)")
