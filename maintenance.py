import os
import libsql_client
from datetime import datetime, timedelta

def clean_up_old_articles():
    print("🧹 開始執行每月資料庫大掃除 (僅清除指定新聞來源 90 日舊文)...")
    
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if not url or not token:
        print("❌ 找不到 Turso 環境變數，停止清理。")
        return
        
    db = libsql_client.create_client_sync(url=url, auth_token=token)
    
    try:
        # ==========================================
        # 🌟 指定清理名單 (黑名單模式：只刪除這些偏向快訊的媒體)
        # ==========================================
        TARGET_SOURCES_TO_CLEAN = [
            "CINRA", "Radii", "VERSE", "WIRED.jp", "触乐"
        ]
        
        # 計算 90 天前的時間門檻
        ninety_days_ago = (datetime.utcnow() - timedelta(days=90)).isoformat()
        
        print("🔍 正在掃描超過 90 天且未被收藏的快訊文章...")
        
        # 抓出所有超過 90 天 且 未被手動收藏 的文章
        res = db.execute("SELECT Link, Source FROM articles WHERE is_bookmarked = 0 AND SortDate < ?", [ninety_days_ago])
        
        # 🌟 邏輯反轉：只要 Source 名稱「包含」在清理名單內，就列入刪除清單
        links_to_delete = [
            row[0] for row in res.rows 
            if any(k in row[1] for k in TARGET_SOURCES_TO_CLEAN)
        ]

        # ==========================================
        # 🚀 執行批次精準抹除
        # ==========================================
        if links_to_delete:
            links_to_delete = list(set(links_to_delete))
            print(f"🗑️ 總共發現 {len(links_to_delete)} 篇符合清理條件的快訊，準備刪除...")
            
            chunk_size = 50
            for i in range(0, len(links_to_delete), chunk_size):
                chunk = links_to_delete[i:i + chunk_size]
                placeholders = ','.join(['?'] * len(chunk))
                sql = f"DELETE FROM articles WHERE Link IN ({placeholders})"
                db.execute(sql, chunk)
                
            print("✅ 大掃除完成，成功釋放 Turso 資料庫空間！(高價值文章已獲保留)")
        else:
            print("✨ 檢查完畢，目前沒有需要清理的過期快訊。")
            
    except Exception as e:
        print(f"❌ 清理過程中發生錯誤: {e}")
    finally:
        db.close()
        print("🔌 資料庫連線已安全關閉。")

if __name__ == "__main__":
    clean_up_old_articles()
