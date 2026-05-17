import streamlit as st
import pandas as pd
from supabase import create_client, Client
import math
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ==========================================
# 1. 介面基礎設定 (唯一全域宣告)
# ==========================================
st.set_page_config(
    page_title="Monoreader Cloud", 
    page_icon="📚", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

SOURCE_URLS = {
    # --- 📚 深度長文 / 評論 ---
    "Aeon 思想誌": "https://aeon.co/",
    "New Yorker, Books and Culture": "https://www.newyorker.com/culture",
    "421 News (EN)": "https://www.421.news/en",
    "421 News (ZH)": "https://www.421.news/zh",
    "聯經思想空間": "https://www.linking.vision/",
    "上海書評": "https://www.thepaper.cn/list_25444",
    "藝術界": "https://www.leapleapleap.com/",
    "MIT Press Reader": "https://thereader.mitpress.mit.edu/",
    "webゲンロン": "https://webgenron.com/",
    "e-flux Journal": "https://www.e-flux.com/journal/",
    "Eurozine": "https://www.eurozine.com/essays/",
    "美術手帖": "https://bijutsutecho.com/magazine/series",
    "澎湃思想市場": "https://www.thepaper.cn/list_25483",
    "Verso Blog": "https://www.versobooks.com/blogs/news",
    "The Point": "https://thepointmag.com/magazine/",
    "The Funambulist": "https://thefunambulist.net/",
    "BIE別的": "https://www.biede.com/",
    "Sabukaru": "https://sabukaru.online/articles", # 🌟 新增：會自動進入最新評論
    
    # --- ⚡ 文化快訊 / 消息 ---
    "WIRED.jp": "https://wired.jp/",
    "CINRA": "https://www.cinra.net/",
    "VERSE": "https://www.verse.com.tw/",
    "界面文化": "https://www.jiemian.com/lists/130.html",
    "Radii": "https://radii.co/" # 🌟 新增：會進入文化快訊
}

# 🌟 排他過濾名單（僅包含快訊媒體，Sabukaru 不在此列）
FAST_NEWS_SOURCES = ["WIRED.jp", "CINRA", "VERSE", "界面文化", "Radii"]

def get_source_link(source_name):
    base_name = source_name.split(" (")[0]
    return SOURCE_URLS.get(base_name, "#")

# ==========================================
# 2. 狀態管理 (Session State)
# ==========================================
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1

def reset_page():
    st.session_state.current_page = 1

def update_page():
    st.session_state.current_page = st.session_state.page_selector

# ==========================================
# 3. 雲端資料庫連線與資料操作
# ==========================================
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

@st.cache_data(ttl=600)
def fetch_data(view_mode, source_filter="全部來源總覽", search_query=""):
    query = supabase.table('articles').select("*")
    
    if search_query:
        query = query.or_(f'Title.ilike.%{search_query}%,Summary.ilike.%{search_query}%')
        if view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽":
            query = query.eq("Source", source_filter)
        elif view_mode == "🔖 我的收藏庫":
            query = query.eq("is_bookmarked", True)
    else:
        if view_mode in ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊"]:
            time_threshold = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            query = query.gte("SortDate", time_threshold)
        elif view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽":
            query = query.eq("Source", source_filter)
        elif view_mode == "🔖 我的收藏庫":
            query = query.eq("is_bookmarked", True)
        
    res = query.order("SortDate", desc=True).limit(500).execute()
    df = pd.DataFrame(res.data)
    
    if df.empty: return df
        
    if view_mode == "✍️ 最新評論":
        mask = df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)
        df = df[~mask]
    elif view_mode == "⚡ 文化快訊":
        mask = df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)
        df = df[mask]
        
    return df

def toggle_bookmark_db(link, current_state):
    try:
        supabase.table('articles').update({"is_bookmarked": not current_state}).eq("Link", link).execute()
        st.cache_data.clear()
        st.toast("書籤狀態已更新！")
    except Exception as e:
        st.error(f"操作失敗: {e}")

# ==========================================
# 🌟 萬能外部文章解析器 (Universal Scraper)
# ==========================================
def fetch_external_article(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        
        og_title = soup.find('meta', property='og:title')
        title = og_title['content'] if og_title and og_title.get('content') else (soup.find('title').get_text() if soup.find('title') else '未知標題')
        
        og_img = soup.find('meta', property='og:image')
        img_url = og_img['content'] if og_img and og_img.get('content') else None
        
        author_meta = soup.find('meta', attrs={'name': 'author'}) or soup.find('meta', property='article:author')
        author = author_meta['content'] if author_meta and author_meta.get('content') else ""
        
        og_desc = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'description'})
        summary = og_desc['content'] if og_desc and og_desc.get('content') else ""
        
        if not summary or len(summary) < 20:
            paragraphs = [p.get_text(strip=True) for p in soup.find_all('p') if len(p.get_text(strip=True)) > 30]
            summary = " ".join(paragraphs[:3]) if paragraphs else "（無法自動擷取摘要文字）"
            
        final_summary = f"**👤 著者：** {author}\n\n{summary}" if author else summary
        if len(final_summary) > 400: final_summary = final_summary[:400] + "..."
        
        return {
            "Source": "🌐 外部手動匯入",
            "Title": title.strip(),
            "Link": url,
            "Published": "手動收藏",
            "Summary": final_summary,
            "Image": img_url,
            "SortDate": datetime.utcnow().isoformat(),
            "is_bookmarked": True
        }
    except Exception as e:
        return None

# ==========================================
# 4. 介面渲染：側邊欄 (Sidebar)
# ==========================================
st.sidebar.title("📚 Monoreader")

search_input = st.sidebar.text_input("🔍 全文搜尋", placeholder="文章、作者或關鍵字...", on_change=reset_page)
st.sidebar.markdown("---")

view_mode = st.sidebar.radio(
    "瀏覽模式", 
    ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊", "🗄️ 分類存檔", "🔖 我的收藏庫", "⏳ 未來典藏"], 
    on_change=reset_page
)
st.sidebar.markdown("---")

with st.sidebar.expander("📥 手動匯入外部文章", expanded=False):
    external_url = st.text_input("貼上文章網址：", placeholder="https://...")
    if st.button("解析並加入收藏庫", use_container_width=True):
        if external_url.startswith("http"):
            with st.spinner("正在解析網頁內容..."):
                art_data = fetch_external_article(external_url)
                if art_data:
                    try:
                        supabase.table('articles').upsert([art_data], on_conflict='Link').execute()
                        st.cache_data.clear()
                        st.success("✅ 已成功解析並加入我的收藏庫！")
                    except Exception as e:
                        st.error("寫入資料庫時發生錯誤。")
                else:
                    st.error("❌ 無法解析該網址，可能是對方網站阻擋了機器人訪問。")
        else:
            st.warning("⚠️ 請輸入包含 http 的完整網址。")

st.sidebar.markdown("---")

selected_source = "全部來源總覽"
if view_mode == "🗄️ 分類存檔":
    st.sidebar.subheader("選擇訂閱來源")
    
    FOLDER_KEYWORDS = ["The Point", "e-flux", "The Funambulist", "421 News"]
    main_options = []
    for src_key in sorted(SOURCE_URLS.keys()):
        if any(k in src_key for k in FOLDER_KEYWORDS):
            folder_name = f"📁 {src_key.split(' (')[0]}"
            if folder_name not in main_options: main_options.append(folder_name)
        else:
            main_options.append(src_key)
            
    main_options.append("🌐 外部手動匯入")
            
    selected_main = st.sidebar.selectbox("請選擇板塊：", ["全部來源總覽"] + main_options, on_change=reset_page)

    if selected_main.startswith("📁 "):
        base_name = selected_main.replace("📁 ", "")
        res = supabase.table('articles').select('Source').ilike('Source', f'%{base_name}%').execute()
        raw_sources = list(set([r['Source'] for r in res.data]))
        
        def extract_issue_number(source_str):
            match = re.search(r'\d+', source_str)
            return int(match.group()) if match else 0
            
        all_sub_sources = sorted(raw_sources, key=extract_issue_number, reverse=True)
        if all_sub_sources:
            selected_source = st.sidebar.radio(f"{base_name} 期號/版本：", all_sub_sources, on_change=reset_page)
    else:
        selected_source = selected_main

# ==========================================
# 5. 介面渲染：主畫面 (Main View)
# ==========================================
if view_mode == "⏳ 未來典藏":
    st.subheader("⏳ 未來典藏 (Future Archive)")
    st.markdown("這裡記錄了已停止更新，但值得未來編寫回溯腳本導入的歷史文化資料庫。")
    st.markdown("---")
    st.markdown("### 🇯🇵 TOKION")
    st.caption("停更於 2024 年。日本前衛流行、藝術與當代潮流次文化的重要指標。")
    st.markdown("🔗 **[前往官網探索](https://tokion.jp/)**")
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🇨🇳 歪腦 Wainao")
    st.caption("停更於 2025 年。專注於新世代華語青年、邊緣視角與深度的社會紀實觀察。")
    st.markdown("🔗 **[前往官網探索](https://www.wainao.me/)**")

else:
    df = fetch_data(view_mode, selected_source, search_input)

    if view_mode == "✨ 全部來源總覽":
        st.subheader(f"✨ 全部來源總覽 (過去 24 小時，共 {len(df)} 篇文章)")
        st.caption("打破雜誌界限，即時串流全平台最新擷取到的文化與思想動態。")
    elif view_mode == "✍️ 最新評論":
        st.subheader(f"✍️ 最新思想與文化評論 (過去 24 小時，共 {len(df)} 篇)")
        st.caption("已自動過濾快訊快報，專注收看國內外深度長文、文獻評論與思想探討（包含 Sabukaru 與 BIE別的）。")
    elif view_mode == "⚡ 文化快訊":
        st.subheader(f"⚡ 文化與藝術快訊 (過去 24 小時，共 {len(df)} 篇)")
        st.caption("聚合 WIRED.jp、CINRA、VERSE、界面文化、Radii 每日高頻更新的即時消息。")
    elif view_mode == "🔖 我的收藏庫":
        st.subheader(f"🔖 我的收藏庫 (共 {len(df)} 篇)")
    else:
        if selected_source != "全部來源總覽":
            st.subheader(f"🗄️ {selected_source} 存檔 (共 {len(df)} 篇)")
            link = get_source_link(selected_source)
            if link != "#": st.markdown(f"🔗 **[前往該雜誌官網閱讀]({link})**")
        else:
            st.subheader(f"🗄️ 全部來源完整存檔 (顯示最新 500 篇)")

    st.markdown("---")

    if df.empty:
        if search_input: st.info("找不到符合關鍵字的文章。")
        else: st.info("過去 24 小時內暫無新文章，請待下次爬蟲執行或查看分類存檔。")
    else:
        PER_PAGE = 20
        total_pages = math.ceil(len(df) / PER_PAGE)
        if st.session_state.current_page > total_pages and total_pages > 0:
            st.session_state.current_page = total_pages
            
        start_idx = (st.session_state.current_page - 1) * PER_PAGE
        end_idx = start_idx + PER_PAGE
        
        for _, row in df.iloc[start_idx:end_idx].iterrows():
            with st.container():
                st.markdown(f"#### [{row['Title']}]({row['Link']})")
                
                col_meta, col_btn = st.columns([5, 1])
                with col_meta:
                    raw_pub = str(row['Published'])
                    sort_date = row.get('SortDate')
                    
                    safe_sort_date = str(sort_date).split('T')[0] if pd.notna(sort_date) and sort_date else "未知時間"
                    display_date = f"擷取於 {safe_sort_date}" if any(k in raw_pub for k in ["最新", "Issue", "刊", "None", "nan"]) else raw_pub
                    st.caption(f"🏷️ {row['Source']} | 🕒 {display_date}")
                
                with col_btn:
                    is_bk = bool(row.get('is_bookmarked', False))
                    st.button("❤️ 已收藏" if is_bk else "🤍 收藏", key=f"btn_{row['Link']}", 
                              on_click=toggle_bookmark_db, args=(row['Link'], is_bk))
                
                if row['Image'] and str(row['Image']).startswith('http'):
                    img_html = f'<img src="{row["Image"]}" style="width:100%; max-width:800px; border-radius:8px; display:block; margin-bottom:15px; object-fit: cover;" loading="lazy">'
                    st.markdown(img_html, unsafe_allow_html=True)
                    
                st.write(row['Summary'])
                st.markdown("---")

        if total_pages > 1:
            st.write("")
            col_space, col_page, col_space2 = st.columns([1, 2, 1])
            with col_page:
                st.selectbox(
                    "📄 選擇頁數 (跳轉至)：", 
                    range(1, total_pages + 1), 
                    index=st.session_state.current_page - 1, 
                    key="page_selector", 
                    on_change=update_page
                )
                st.caption(f"目前顯示第 {st.session_state.current_page} 頁，共 {total_pages} 頁")

st.sidebar.markdown("---")
st.sidebar.caption("Monoreader Cloud v2.3 (Universal Clipper)")
