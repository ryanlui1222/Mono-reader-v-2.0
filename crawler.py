import feedparser
import pandas as pd
from bs4 import BeautifulSoup
import concurrent.futures
import cloudscraper
import urllib.parse
import re
import json

# ==========================================
# 全局網路引擎
# ==========================================
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

# ==========================================
# 爬蟲模組區
# ==========================================
def fetch_rss(feed_url, source_name, limit=20, deep_fetch=False):
    """萬用 RSS 抓取：上限提高至 20 篇（可由參數控制）"""
    articles = []
    try:
        res = scraper.get(feed_url, timeout=15)
        parsed = feedparser.parse(res.content)
        # 🌟 修改點：根據傳入的 limit 決定抓取數量
        entries = parsed.entries[:limit] 
        
        def process_entry(entry):
            raw_text = entry.content[0].value if 'content' in entry else entry.get('summary', '')
            soup = BeautifulSoup(raw_text, 'html.parser')
            text = soup.get_text(separator=" ", strip=True)
            
            img = soup.find('img')
            img_url = img['src'] if img and 'src' in img.attrs else None
            
            if img_url:
                img_url = urllib.parse.urljoin(entry.link, img_url)
            
            if deep_fetch:
                try:
                    art_res = scraper.get(entry.link, timeout=10)
                    art_soup = BeautifulSoup(art_res.text, 'html.parser')
                    
                    if not img_url:
                        og_img = art_soup.find('meta', attrs={'property': 'og:image'})
                        if og_img and og_img.get('content'):
                            img_url = og_img['content']
                            
                    paragraphs = [p.get_text(separator=" ", strip=True) for p in art_soup.find_all('p') if len(p.get_text(strip=True)) > 60]
                    if paragraphs:
                        clean_p = [p for p in paragraphs if not any(bad in p.lower() for bad in ["subscribe", "newsletter", "sign up", "cookie"])]
                        if clean_p:
                            text = " ".join(clean_p[:3])
                except:
                    pass 
            
            eng_count = sum(1 for c in text[:50] if 'a' <= c.lower() <= 'z' or 'A' <= c.upper() <= 'Z')
            max_len = 600 if eng_count > 25 else 200 
            display_text = text[:max_len] + '...' if len(text) > max_len else text
            
            return {
                "Source": source_name,
                "Title": entry.title,
                "Link": entry.link,
                "Published": entry.get('published', '最新'),
                "Summary": display_text,
                "Image": img_url
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(process_entry, entry) for entry in entries]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result: articles.append(result)
                
    except Exception as e:
        print(f"{source_name} 抓取失敗: {e}")
    return articles


def fetch_funambulist():
    """The Funambulist：自動抓取最新一期的【所有】文章"""
    issues_url = "https://thefunambulist.net/magazine/issues"
    articles = []
    try:
        soup = BeautifulSoup(scraper.get(issues_url, timeout=15).text, 'html.parser')
        latest_issue_url = None
        invalid_paths = ['geo-index', 'stockists', 'subscribe', 'shop', 'podcast', 'editorials', 'network']
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if '/magazine/' in href and not any(bad in href for bad in invalid_paths):
                clean_href = href.rstrip('/')
                if not clean_href.endswith('/magazine') and not clean_href.endswith('/magazine/issues'):
                    latest_issue_url = href if href.startswith('http') else f"https://thefunambulist.net{href}"
                    break 
                
        if not latest_issue_url: return articles 
            
        soup_issue = BeautifulSoup(scraper.get(latest_issue_url, timeout=15).text, 'html.parser')
        h1_tag = soup_issue.find('h1')
        issue_title = h1_tag.get_text(strip=True) if h1_tag else "最新刊"
        source_name = f"The Funambulist ({issue_title})"
        
        def process_funambulist_link(a_tag):
            href = a_tag['href']
            title = a_tag.get_text(strip=True)
            try:
                art_soup = BeautifulSoup(scraper.get(href, timeout=15).text, 'html.parser')
                paragraphs = [p.get_text(strip=True) for p in art_soup.find_all('p') if len(p.get_text(strip=True)) > 80]
                summary = " ".join(paragraphs)[:600] + "..." if paragraphs else "（本文無提供文字摘要）"
            except Exception:
                summary = "（摘要載入超時）"
                
            return {
                "Source": source_name, "Title": title, "Link": href,
                "Published": issue_title, "Summary": summary, "Image": None
            }

        valid_links = []
        seen_titles = set()
        bad_title_keywords = ['subscribe', 'subscribing', 'introduction', 'editorial', 'about', 'shop']
        
        for a_tag in soup_issue.find_all('a', href=True):
            href = a_tag['href']
            title = a_tag.get_text(strip=True)
            if len(title) > 10 and href.startswith('https://thefunambulist.net/') and title.lower() != "the funambulist":
                if not any(bad_word in title.lower() for bad_word in bad_title_keywords):
                    if title not in seen_titles:
                        valid_links.append(a_tag)
                        seen_titles.add(title)
                # 🌟 修改點：移除了 if len(valid_links) >= 8: break，讓它抓完這期所有文章
                
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(process_funambulist_link, a) for a in valid_links]
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res: articles.append(res)
                
    except Exception as e:
        print(f"Funambulist 抓取失敗: {e}")
    return articles


def fetch_webgenron():
    """Webゲンロン：抓取首頁最新發布的所有文章 (設安全上限15篇)"""
    url = "https://webgenron.com/"
    articles = []
    try:
        res = scraper.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        seen_links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/articles/' in href and not href.endswith('/articles') and not href.endswith('/articles/'):
                title = a.get_text(strip=True)
                if len(title) < 8 or href in seen_links: continue
                seen_links.add(href)
                full_link = f"https://webgenron.com{href}" if href.startswith('/') else href
                
                try:
                    art_soup = BeautifulSoup(scraper.get(full_link, timeout=5).text, 'html.parser')
                    desc = art_soup.find('meta', attrs={'name': 'description'}) or art_soup.find('meta', attrs={'property': 'og:description'})
                    summary = desc['content'][:200] + "..." if desc else "（點擊標題閱讀原文）"
                except:
                    summary = "（摘要載入超時）"
                
                articles.append({
                    "Source": "webゲンロン", "Title": title, "Link": full_link,
                    "Published": "最新", "Summary": summary, "Image": None
                })
                # 🌟 修改點：將上限從 8 提高到 15，確保能涵蓋首頁所有的近期更新，同時避免爬到無關的舊連結
                if len(articles) >= 15: break
    except Exception as e:
        print(f"webゲンロン 抓取失敗: {e}")
    return articles


def fetch_eflux():
    """e-flux Journal：抓取當期【所有】文章"""
    url = "https://www.e-flux.com/journal/"
    articles = []
    try:
        res = scraper.get(url, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        issue_links = []
        for a in soup.find_all('a', href=True):
            match = re.match(r'^/journal/(\d+)$', a['href'])
            if match:
                issue_links.append((int(match.group(1)), a['href']))
                
        if not issue_links:
            return articles
            
        latest_issue_path = sorted(issue_links, reverse=True)[0][1]
        latest_issue_url = f"https://www.e-flux.com{latest_issue_path}"
        
        issue_res = scraper.get(latest_issue_url, timeout=10)
        issue_soup = BeautifulSoup(issue_res.text, 'html.parser')
        
        for card in issue_soup.find_all('div', class_='preview-journalarticle'):
            title_tag = card.find('a', class_='preview-journalarticle__title')
            if not title_tag: continue
                
            title = title_tag.get_text(strip=True)
            href = title_tag['href']
            full_link = f"https://www.e-flux.com{href}" if href.startswith('/') else href
            
            author_tag = card.find('div', class_='preview-journalarticle__author')
            author = author_tag.get_text(strip=True) if author_tag else ""
            
            text_tag = card.find('div', class_='preview-journalarticle__text')
            if text_tag:
                raw_html = str(text_tag)
                extracted_p = re.findall(r'<p[^>]*>(.*?)</p>', raw_html)
                if extracted_p:
                    summary_text = " ".join([BeautifulSoup(p, "html.parser").get_text() for p in extracted_p])
                else:
                    summary_text = text_tag.get_text(separator=" ", strip=True)
            else:
                summary_text = "（請點擊標題閱讀原文）"

            blacklisted_words = ["subscribe", "education announces", "newsletter"]
            if any(bad_word in summary_text.lower() for bad_word in blacklisted_words):
                continue
            
            img_tag = card.find('img')
            img_url = img_tag['src'] if img_tag and 'src' in img_tag.attrs else None
            
            if author:
                summary = f"**👤 著者：** {author}\n\n{summary_text}"
            else:
                summary = summary_text
                
            articles.append({
                "Source": "e-flux Journal",
                "Title": title,
                "Link": full_link,
                "Published": "最新刊",
                "Summary": summary,
                "Image": img_url
            })
            
            # 🌟 修改點：移除了 if len(articles) >= 8: break，讓它抓完該期雜誌的所有卡片
                
    except Exception as e:
        print(f"e-flux 抓取失敗: {e}")
    return articles

def main():
    print("🚀 開始執行資料抓取...")
    all_articles = []
    
    # 🌟 修改點：將 RSS 的抓取數量提高至 15 或 20 篇
    rss_sources = [
        ("https://aeon.co/feed.rss", "Aeon 思想誌", 15, True),
        ("https://www.newyorker.com/feed/culture/rss", "New Yorker, Books and Culture", 15, True),
        ("https://www.421.news/zh/rss", "421 News", 15, False),
        ("https://www.linking.vision/feed/", "聯經思想空間", 15, False),
        ("https://feedx.net/rss/shanghaishuping.xml", "上海書評", 15, False),
        ("https://www.leapleapleap.com/feed/", "藝術界", 15, False),
        ("https://thereader.mitpress.mit.edu/feed/", "MIT Press Reader", 15, True)
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # 注意這裡傳入了 limit 參數
        futures = [executor.submit(fetch_rss, url, name, limit, deep) for url, name, limit, deep in rss_sources]
        
        futures.extend([
            executor.submit(fetch_webgenron), 
            executor.submit(fetch_eflux),
            executor.submit(fetch_funambulist) 
        ])
        
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result: all_articles.extend(result)

    df = pd.DataFrame(all_articles)
    
    if not df.empty:
        def parse_date(date_str):
            if pd.isna(date_str) or "最新" in str(date_str): return pd.Timestamp.now(tz='UTC')
            try: return pd.to_datetime(date_str, utc=True)
            except: return pd.Timestamp('2000-01-01', tz='UTC')
            
        df['SortDate'] = df['Published'].apply(parse_date)
        df = df.sort_values(by='SortDate', ascending=False).reset_index(drop=True)
        df = df.drop(columns=['SortDate'])
        
        df.to_json("data.json", orient="records", force_ascii=False, indent=4)
        print(f"✅ 成功抓取 {len(df)} 篇文章，已儲存至 data.json")
    else:
        print("❌ 未抓取到任何資料。")

if __name__ == "__main__":
    main()
