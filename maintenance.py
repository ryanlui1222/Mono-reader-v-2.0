import os
import libsql_client
from datetime import datetime, timedelta

def clean_up_old_articles():
    print("🧹 開始執行每週資料庫大掃除 (統一 30 日代謝版)...")
    
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if not url or not token:
        print("❌ 找不到 Turso 環境變數，停止清理。")
        return
        
    db = libsql_client.create_client_sync(url=url, auth_token=token)
    
    try:
        # ==========================================
        # 🌟 擴充的永久保護名單 (白名單)
        # ==========================================
        PROTECTED_SOURCES = [
            "The Point", "e-flux", "The Funambulist", "TripleAmpersand", 
            "421 News", "Verso Blog", "MIT Press Reader"
        ]
        
        # 計算 30 天前的時間門檻
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        
        print("🔍 正在掃描超過 30 天且未被收藏的文章...")
        
        # 抓出所有超過 30 天 且 未被手動收藏 的文章
        res = db.execute("SELECT Link, Source FROM articles WHERE is_bookmarked = 0 AND SortDate < ?", [thirty_days_ago])
        
        # 過濾邏輯：只要 Source 名稱「不包含」在白名單內，就列入刪除清單
        links_to_delete = [
            row[0] for row in res.rows 
            if not any(k in row[1] for k in PROTECTED_SOURCES)
        ]

        # ==========================================
        # 🚀 執行批次精準抹除
        # ==========================================
        if links_to_delete:
            links_to_delete = list(set(links_to_delete))
            print(f"🗑️ 總共發現 {len(links_to_delete)} 篇符合清理條件的文章，準備刪除...")
            
            chunk_size = 50
            for i in range(0, len(links_to_delete), chunk_size):
                chunk = links_to_delete[i:i + chunk_size]
                placeholders = ','.join(['?'] * len(chunk))
                sql = f"DELETE FROM articles WHERE Link IN ({placeholders})"
                db.execute(sql, chunk)
                
            print("✅ 大掃除完成，成功釋放 Turso 資料庫空間！")
        else:
            print("✨ 檢查完畢，目前沒有需要清理的過期文章。")
            
    except Exception as e:
        print(f"❌ 清理過程中發生錯誤: {e}")

if __name__ == "__main__":
    clean_up_old_articles()
