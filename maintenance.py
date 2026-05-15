import os
from supabase import create_client, Client
from datetime import datetime, timedelta

def clean_up_old_articles():
    print("🧹 開始執行每月資料庫大掃除...")
    
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("❌ 找不到 Supabase 環境變數，停止清理。")
        return
        
    supabase: Client = create_client(url, key)
    
    # 定義保留條件
    PROTECTED_SOURCES = ["The Point", "e-flux", "The Funambulist"]
    six_months_ago = (datetime.utcnow() - timedelta(days=180)).isoformat()
    
    try:
        # 從資料庫抓取「候選名單」
        res = supabase.table('articles') \
            .select('Link, Source') \
            .eq('is_bookmarked', False) \
            .lt('SortDate', six_months_ago) \
            .execute()
            
        candidates = res.data
        if not candidates:
            print("✨ 目前沒有需要清理的舊文章。")
            return

        # 白名單過濾
        links_to_delete = []
        for article in candidates:
            is_protected = any(keyword in article['Source'] for keyword in PROTECTED_SOURCES)
            if not is_protected:
                links_to_delete.append(article['Link'])

        # 執行批次刪除
        if links_to_delete:
            print(f"🗑️ 發現 {len(links_to_delete)} 篇過期文章，準備刪除...")
            chunk_size = 50
            for i in range(0, len(links_to_delete), chunk_size):
                chunk = links_to_delete[i:i + chunk_size]
                supabase.table('articles').delete().in_('Link', chunk).execute()
            print("✅ 大掃除完成，成功釋放資料庫空間！")
        else:
            print("✨ 候選文章皆為受保護的期刊，無需刪除。")
            
    except Exception as e:
        print(f"❌ 清理過程中發生錯誤: {e}")

if __name__ == "__main__":
    clean_up_old_articles()
