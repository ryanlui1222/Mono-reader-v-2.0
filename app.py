import streamlit as st
from views import view_monoreader, view_biblioapp, view_mediavault, view_omnivault

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
    # 🌟 主選單 (加入萬物收藏匣)
    app_mode = st.radio(
        "切換平台模組", 
        ["📚 Monoreader", "🎓 Biblioapp", "🎬 Media Vault", "🗃️ 萬物收藏匣"], 
        label_visibility="collapsed"
    )
    
    st.markdown("---")

    # 🌟 爬蟲健康度指示燈
    import core_utils
    from datetime import datetime
    
    health_data = core_utils.fetch_crawler_health()
    if health_data:
        has_error = False
        error_list = []
        
        for row in health_data:
            # 計算距離最後一次檢查的時間差 (小時)
            try:
                # 處理 ISO 格式時間 (相容 Python 各版本)
                clean_iso = row['last_check'].replace('Z', '+00:00')
                last_check_dt = datetime.fromisoformat(clean_iso).replace(tzinfo=None)
                hours_diff = (datetime.utcnow() - last_check_dt).total_seconds() / 3600
            except:
                hours_diff = 0

            # 判斷異常：直接報錯，或超過 48 小時未更新 (靜默失敗)
            if row.get('status') == 'ERROR':
                has_error = True
                error_list.append(f"🔴 **{row['source_name']}**: 程式崩潰 ({row.get('error_msg','')})")
            elif hours_diff > 48:
                has_error = True
                error_list.append(f"🟡 **{row['source_name']}**: 超過 {int(hours_diff)} 小時未成功抓取新文")

        # 渲染燈號與面板
        if has_error:
            with st.expander("🚨 爬蟲系統異常", expanded=True):
                for err in error_list:
                    st.caption(err)
        else:
            with st.expander("🟢 系統健康度：良好", expanded=False):
                st.caption("所有來源皆在 48 小時內成功更新。")
                st.caption(f"最後檢查時間: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} (UTC)")

# ==========================================
# 3. 模組渲染導流
# ==========================================
if app_mode == "📚 Monoreader":
    view_monoreader.render_page()
elif app_mode == "🎓 Biblioapp":
    view_biblioapp.render_page()
elif app_mode == "🎬 Media Vault":
    view_mediavault.render_page() 
elif app_mode == "🗃️ 萬物收藏匣":
    view_omnivault.render_page()  # 🌟 導流至萬物收藏匣

st.sidebar.markdown("---")
st.sidebar.caption("Monoreader Cloud v5.0 (Omni-Vault Edition)")
