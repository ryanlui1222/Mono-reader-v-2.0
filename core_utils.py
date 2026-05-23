import streamlit as st
import pandas as pd
import libsql_client
import math
import re
import requests
import cloudscraper
import base64
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

SOURCE_URLS = {
    "Aeon 思想誌": "https://aeon.co/", "New Yorker, Books and Culture": "https://www.newyorker.com/culture",
    "421 News (EN)": "https://www.421.news/en", "421 News (ZH)": "https://www.421.news/zh",
    "聯經思想空間": "https://www.linking.vision/", "上海書評": "https://www.thepaper.cn/list_25444",
    "藝術界": "https://www.leapleapleap.com/", "MIT Press Reader": "https://thereader.mitpress.mit.edu/",
    "webゲンロン": "https://webgenron.com/", "e-flux Journal": "https://www.e-flux.com/journal/",
    "Eurozine": "https://www.eurozine.com/essays/", "美術手帖": "https://bijutsutecho.com/magazine/series",
    "澎湃思想市場": "https://www.thepaper.cn/list_25483", "Verso Blog": "https://www.versobooks.com/blogs/news",
    "The Point": "https://thepointmag.com/magazine/", "The Funambulist": "https://thefunambulist.net/",
    "BIE別的": "https://www.biede.com/", "Sabukaru": "https://sabukaru.online/articles", 
    "TripleAmpersand": "https://tripleampersand.org/", "WIRED.jp": "https://wired.jp/",
    "CINRA": "https://www.cinra.net/", "VERSE": "https://www.verse.com.tw/",
    "界面文化": "https://www.jiemian.com/lists/130.html", "Radii": "https://radii.co/",
    "Duke Arts & Humanities": "https://today.duke.edu/arts-humanities",
    "Asian Review of Books": "https://asianreviewofbooks.com/"
}
FAST_NEWS_SOURCES = ["WIRED.jp", "CINRA", "VERSE", "界面文化", "Radii", "触乐", "FNMNL"]

def get_source_link(source_name): return SOURCE_URLS.get(source_name.split(" (")[0], "#")

@st.cache_resource
def init_connection(): return libsql_client.create_client_sync(url=st.secrets["TURSO_DATABASE_URL"], auth_token=st.secrets["TURSO_AUTH_TOKEN"])
db = init_connection()

@st.cache_data(ttl=600)
def fetch_data(view_mode, source_filter="全部來源總覽", search_query=""):
    sql, args = "SELECT * FROM articles WHERE 1=1", []
    if search_query:
        sql += " AND (Title LIKE ? OR Summary LIKE ?)"; args.extend([f"%{search_query}%", f"%{search_query}%"])
        if view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽": sql += " AND Source = ?"; args.append(source_filter)
        elif view_mode == "🔖 我的收藏庫": sql += " AND is_bookmarked = 1"
    else:
        if view_mode in ["✨ 全部來源總覽", "✍️ 最新評論", "⚡ 文化快訊"]: sql += " AND SortDate >= ?"; args.append((datetime.utcnow() - timedelta(hours=24)).isoformat())
        elif view_mode == "🗄️ 分類存檔" and source_filter != "全部來源總覽": sql += " AND Source = ?"; args.append(source_filter)
        elif view_mode == "🔖 我的收藏庫": sql += " AND is_bookmarked = 1"
    sql += " ORDER BY SortDate DESC LIMIT 500"
    res = db.execute(sql, args)
    if not res.rows: return pd.DataFrame()
    df = pd.DataFrame([dict(zip(res.columns, row)) for row in res.rows])
    if view_mode == "✍️ 最新評論": df = df[~df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)]
    elif view_mode == "⚡ 文化快訊": df = df[df['Source'].str.contains('|'.join(FAST_NEWS_SOURCES), case=False, na=False)]
    return df

@st.cache_data(ttl=600)
def fetch_academic_pubs(view_mode="探索", pub_type="Book", source_filter="總覽"):
    sql, args = "SELECT * FROM academic_pubs WHERE 1=1", []
    
    if view_mode == "🔖 待讀書架":
        sql += " AND is_bookmarked = 1 AND type != 'Web Link'"
    elif view_mode == "🔗 網址備存":
        sql += " AND type = 'Web Link'"
    else:
        sql += " AND type = ?"; args.append(pub_type)
        
        if source_filter == "📥 剛匯入 (未收藏)":
            sql += " AND is_bookmarked = 0"
        elif source_filter != "總覽 (依日期遞減)": 
            sql += " AND publisher_journal = ?"; args.append(source_filter)
            
    sql += " ORDER BY publish_date DESC LIMIT 500"
    res = db.execute(sql, args)
    if not res.rows: return pd.DataFrame()
    return pd.DataFrame([dict(zip(res.columns, row)) for row in res.rows])

def toggle_bookmark_db(link, current_state):
    try: db.execute("UPDATE articles SET is_bookmarked = ? WHERE Link = ?", [0 if current_state else 1, link]); st.cache_data.clear(); st.toast("書籤更新！")
    except Exception as e: st.error(f"操作失敗: {e}")

def delete_article_db(link):
    try: db.execute("DELETE FROM articles WHERE Link = ?", [link]); st.cache_data.clear(); st.toast("🗑️ 文章已抹除！")
    except Exception as e: st.error(f"刪除失敗: {e}")

def toggle_biblio_bookmark_db(pub_id, current_state):
    try: db.execute("UPDATE academic_pubs SET is_bookmarked = ? WHERE id = ?", [0 if current_state else 1, pub_id]); st.cache_data.clear(); st.toast("書架狀態更新！")
    except Exception as e: st.error(f"操作失敗: {e}")

def delete_biblio_db(pub_id):
    try: db.execute("DELETE FROM academic_pubs WHERE id = ?", [pub_id]); st.cache_data.clear(); st.toast("🗑️ 紀錄已徹底刪除！")
    except Exception as e: st.error(f"刪除失敗: {e}")

def fetch_custom_resources(module_name):
    res = db.execute("SELECT * FROM custom_resources WHERE module = ? ORDER BY added_date DESC", [module_name])
    return pd.DataFrame([dict(zip(res.columns, row)) for row in res.rows]) if res.rows else pd.DataFrame()

def add_custom_resource(module_name, url):
    if not url.startswith("http"): return False, "⚠️ 請輸入完整的網址 (包含 http)"
    title = "未命名網站"
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        res = scraper.get(url, timeout=15)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            if soup.find('meta', property='og:title'): 
                title = soup.find('meta', property='og:title').get('content')
            elif soup.find('meta', attrs={'name': 'twitter:title'}): 
                title = soup.find('meta', attrs={'name': 'twitter:title'}).get('content')
            elif soup.find('title'): 
                title = soup.find('title').get_text()
            if title and title != "未命名網站":
                title = title.split('|')[0].split(' - ')[0].strip()
            else:
                title = "未命名網站"
    except Exception as e:
        print(f"⚠️ 標題擷取失敗 ({e})，轉為手動命名模式。")
    try:
        db.execute("INSERT INTO custom_resources (module, title, url, added_date) VALUES (?, ?, ?, ?) ON CONFLICT(url) DO UPDATE SET title=excluded.title", 
                   [module_name, title, url, datetime.utcnow().isoformat()])
        st.cache_data.clear()
        return True, f"✅ 已成功加入清單！(若名稱不如預期，請點擊右側管理修改)"
    except Exception as e:
        return False, f"❌ 資料庫寫入錯誤: {e}"

def update_custom_resource(res_id, new_title, new_comment=""):
    try:
        db.execute("UPDATE custom_resources SET title = ?, comment = ? WHERE id = ?", [new_title, new_comment, res_id])
        st.cache_data.clear(); st.toast("✏️ 網站資訊與備註已更新！")
    except Exception as e: st.error(f"更新失敗: {e}")

def delete_custom_resource(res_id):
    try:
        db.execute("DELETE FROM custom_resources WHERE id = ?", [res_id])
        st.cache_data.clear(); st.toast("🗑️ 網站已從清單中移除！")
    except Exception as e: st.error(f"刪除失敗: {e}")

def get_secure_image_base64(img_url, source=""):
    if not img_url: return ""
    if str(img_url).startswith("data:image"): return img_url
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        headers = {"User-Agent": "Mozilla/5.0"}
        if source == "douban": headers["Referer"] = "https://book.douban.com/"
        res = scraper.get(img_url, headers=headers, timeout=10)
        if res.status_code == 200 and len(res.content) > 500:
            return f"data:{res.headers.get('Content-Type', 'image/jpeg')};base64,{base64.b64encode(res.content).decode('utf-8')}"
    except: pass
    return img_url

def fetch_google_fallback(isbn):
    try:
        res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}", timeout=5).json()
        if "items" in res and len(res["items"]) > 0:
            info = res["items"][0].get("volumeInfo", {})
            img = info.get("imageLinks", {}).get("thumbnail", "").replace("http://", "https://")
            return {
                "type": "Book", "title": info.get("title", "未命名書籍"), "author": ", ".join(info.get("authors", [])),
                "publisher_journal": info.get("publisher", "手動加入"), "issue_volume": "", "identifier": isbn, 
                "publish_date": info.get("publishedDate", datetime.utcnow().strftime("%Y-%m-%d")),
                "abstract": info.get("description", "（無摘要）")[:600], "link": info.get("infoLink", ""),
                "image": get_secure_image_base64(img, "google"), "is_bookmarked": 0
            }
    except: pass
    return None

def fetch_openbd(isbn):
    try:
        res = requests.get(f"https://api.openbd.jp/v1/get?isbn={isbn}", timeout=10).json()
        if res and res[0]:
            info = res[0].get("summary", {})
            img_url = get_secure_image_base64(info.get("cover", ""), "openbd") if info.get("cover") else get_secure_image_base64(f"https://www.hanmoto.com/bd/img/{isbn}.jpg", "hanmoto")
            return {
                "type": "Book", "title": info.get("title", "未命名"), "author": info.get("author", "未知"),
                "publisher_journal": info.get("publisher", "手動加入"), "issue_volume": "", "identifier": isbn, 
                "publish_date": info.get("pubdate", datetime.utcnow().strftime("%Y-%m-%d")), "abstract": "（日文出版品）",
                "link": f"https://ndlsearch.ndl.go.jp/books/R100000002-I{isbn}", "image": img_url, "is_bookmarked": 0
            }
    except: pass
    return fetch_google_fallback(isbn)

def fetch_douban(isbn):
    url = f"https://book.douban.com/isbn/{isbn}/"
    try:
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
        res = scraper.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            title = soup.find("span", property="v:itemreviewed").text.strip() if soup.find("span", property="v:itemreviewed") else "未知"
            mainpic = soup.find("div", id="mainpic")
            img_url = get_secure_image_base64(mainpic.find("img").get("src", "").replace("/s/public/", "/l/public/"), "douban") if mainpic and mainpic.find("img") else ""
            author_span = soup.find("span", string=re.compile("作者"))
            author = author_span.find_next("a").text.strip() if author_span and author_span.find_next("a") else "未知"
            pub_span = soup.find("span", string=re.compile("出版社"))
            publisher = pub_span.next_sibling.strip().replace(":", "").strip() if pub_span and pub_span.next_sibling else "手動加入"
            intro = soup.find("div", class_="intro")
            abstract = intro.text.strip().replace("\n", " ") if intro else "（無摘要）"
            return {
                "type": "Book", "title": title, "author": author, "publisher_journal": publisher, "issue_volume": "", 
                "identifier": isbn, "publish_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "abstract": abstract[:600], "link": url, "image": img_url, "is_bookmarked": 0
            }
    except: pass
    return fetch_google_fallback(isbn)

def fetch_book_by_isbn(isbn):
    clean_isbn = re.sub(r'[^0-9X]', '', str(isbn).upper())
    if not clean_isbn: return None
    if clean_isbn.startswith("9784") or clean_isbn.startswith("9794"): return fetch_openbd(clean_isbn)
    elif clean_isbn.startswith("9787") or clean_isbn.startswith("978957") or clean_isbn.startswith("978986") or clean_isbn.startswith("978626"): return fetch_douban(clean_isbn)
    
    best_cover = ""
    try:
        syn_res = requests.get(f"https://syndetics.com/index.aspx?isbn={clean_isbn}/lc.jpg&client=test", timeout=5)
        if syn_res.status_code == 200 and len(syn_res.content) > 100: best_cover = f"https://syndetics.com/index.aspx?isbn={clean_isbn}/lc.jpg&client=test"
    except: pass

    res = fetch_google_fallback(clean_isbn)
    if res:
        if best_cover: res["image"] = best_cover
        return res
        
    try:
        ol_data = requests.get(f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean_isbn}&format=json&jscmd=data", timeout=5).json()
        if f"ISBN:{clean_isbn}" in ol_data:
            info = ol_data[f"ISBN:{clean_isbn}"]
            authors = [a.get("name", "") for a in info.get("authors", [])]
            return {
                "type": "Book", "title": info.get("title", "未命名"), "author": ", ".join(authors) or "未知",
                "publisher_journal": info.get("publishers", [{"name": "手動加入"}])[0].get("name", "手動加入"), "issue_volume": "",
                "identifier": clean_isbn, "publish_date": info.get("publish_date", datetime.utcnow().strftime("%Y-%m-%d")),
                "abstract": "（Open Library 匯入）", "link": info.get("url", ""), 
                "image": best_cover if best_cover else info.get("cover", {}).get("large", f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"), "is_bookmarked": 0
            }
    except: pass
    return None

def fetch_book_by_url(url):
    if not url.startswith("http"): return None
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    try:
        res = scraper.get(url, timeout=15)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            og_title = soup.find('meta', property='og:title')
            title = og_title['content'] if og_title and og_title.get('content') else (soup.find('title').get_text() if soup.find('title') else '未命名書籍')
            title = title.split('|')[0].split(' - ')[0].replace('Amazon.co.jp:', '').replace('Amazon.com:', '').strip()
            
            og_img = soup.find('meta', property='og:image')
            img_url = og_img['content'] if og_img and og_img.get('content') else ""
            if img_url: img_url = get_secure_image_base64(img_url, "url_backup")
            
            author_meta = soup.find('meta', attrs={'name': 'author'}) or soup.find('meta', property='article:author')
            author = author_meta['content'] if author_meta and author_meta.get('content') else ""
            if not author:
                for p in soup.find_all(['p', 'span', 'a'], class_=re.compile(r'author|byline', re.I)):
                    p_text = p.get_text(strip=True)
                    if p_text and len(p_text) < 50:
                        author = p_text
                        break
            if not author: author = "未知作者"
            
            og_desc = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'description'})
            abstract = og_desc['content'] if og_desc and og_desc.get('content') else ""
            
            url_hash = f"url_{id(url)}"
            match = re.search(r'dp/([A-Z0-9]{10})|product/([A-Z0-9]{10})|asin/([A-Z0-9]{10})', url, re.I)
            if match: url_hash = f"amazon_{match.group(1) or match.group(2) or match.group(3)}"

            return {
                "type": "Web Link", "title": title, "author": author, "publisher_journal": "網頁備存", 
                "issue_volume": "", "identifier": url_hash, "publish_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "abstract": abstract[:600] if abstract else "（透過外部網址備存導入）", "link": url, 
                "image": img_url, "is_bookmarked": 0
            }
    except Exception as e:
        print(f"網址備存解析失敗: {e}")
    return None
    
def fetch_external_article(url):
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    try:
        res = scraper.get(url, timeout=15)
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
        return {"Source": "🌐 外部手動匯入", "Title": title.strip(), "Link": url, "Published": "手動收藏", "Summary": final_summary, "Image": img_url, "SortDate": datetime.utcnow().isoformat(), "is_bookmarked": 1}
    except: return None
