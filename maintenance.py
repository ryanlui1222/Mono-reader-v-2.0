import os
from supabase import create_client, Client
from datetime import datetime, timedelta

def clean_up_old_articles():
    print("🧹 開始執行每週資料庫分級大掃除...")
    
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("❌ 找不到 Supabase 環境變數，停止清理。")
        return
        
    supabase: Client = create_client(url, key)
    
    try:
        # ==========================================
        # 🌟 級別一：快快訊息 (超過 7 天 且 未收藏 則清理)
        # ==========================================
        FAST_CLEANUP_SOURCES = ["WIRED.jp", "CINRA", "VERSE", "界面文化", "Radii"]
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        
        print("🔍 正在掃描過期的文化快訊 (7天門檻)...")
        res_fast = supabase.table('articles') \
            .select('Link, Source') \
            .eq('is_bookmarked', False) \
            .lt('SortDate', seven_days_ago) \
            .execute()
            
        # 只要 Source 名稱包含快訊關鍵字，就列入刪除名單
        links_to_delete = [
            art['Link'] for art in res_fast.data 
            if any(k in art['Source'] for k in FAST_CLEANUP_SOURCES)
        ]

        # ==========================================
        # 🌟 級別二：常規深度評論 (超過 180 天 且 未收藏 則清理)
        # ==========================================
        PROTECTED_SOURCES = ["The Point", "e-flux", "The Funambulist", "TripleAmpersand"]
        six_months_ago = (datetime.utcnow() - timedelta(days=180)).isoformat()
        
        print("🔍 正在掃描過期的深度長文 (180天門檻)...")
        res_normal = supabase.table('articles') \
            .select('Link, Source') \
            .eq('is_bookmarked', False) \
            .lt('SortDate', six_months_ago) \
            .execute()
            
        # 排除三大永久保留期刊，其餘常規長文列入刪除名單
        normal_links = [
            art['Link'] for art in res_normal.data 
            if not any(k in art['Source'] for k in PROTECTED_SOURCES + FAST_CLEANUP_SOURCES)
        ]
        links_to_delete.extend(normal_links)

        # ==========================================
        # 🚀 執行批次精準抹除
        # ==========================================
        if links_to_delete:
            links_to_delete = list(set(links_to_delete)) # 去除重複項
            print(f"🗑️ 總共發現 {len(links_to_delete)} 篇符合清理條件的文章，準備刪除...")
            chunk_size = 50
            for i in range(0, len(links_to_delete), chunk_size):
                chunk = links_to_delete[i:i + chunk_size]
                supabase.table('articles').delete().in_('Link', chunk).execute()
            print("✅ 大掃除完成，成功釋放雲端資料庫空間！")
        else:
            print("✨ 檢查完畢，目前資料庫內沒有任何過期文章。")
            
    except Exception as e:
        print(f"❌ 清理過程中發生錯誤: {e}")

if __name__ == "__main__":
    clean_up_old_articles()
