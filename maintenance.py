import os
import libsql_client
from datetime import datetime, timedelta

def clean_up_old_articles():
    print("🧹 開始執行每週資料庫分級大掃除 (Turso 版本)...")
    
    # 讀取 Turso 環境變數
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if not url or not token:
        print("❌ 找不到 Turso 環境變數，停止清理。")
        return
        
    # 建立 Turso 連線
    db = libsql_client.create_client_sync(url=url, auth_token=token)
    
    try:
        # ==========================================
        # 🌟 定義清理與保護名單
        # ==========================================
        FAST_CLEANUP_SOURCES = ["WIRED.jp", "CINRA", "VERSE", "界面文化", "Radii"]
        PROTECTED_SOURCES = ["The Point", "e-flux", "The Funambulist", "TripleAmpersand"]
        
        # 計算時間門檻 (轉為 ISO 格式字串，SQLite 可直接比對大小)
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        six_months_ago = (datetime.utcnow() - timedelta(days=180)).isoformat()
        
        links_to_delete = []

        # ==========================================
        # 🗑️ 級別一：過期文化快訊 (超過 7 天 且 未收藏)
        # ==========================================
        print("🔍 正在掃描過期的文化快訊 (7天門檻)...")
        # 註：SQLite 中 0 代表 False
        res_fast = db.execute("SELECT Link, Source FROM articles WHERE is_bookmarked = 0 AND SortDate < ?", [seven_days_ago])
        
        fast_links = [
            row[0] for row in res_fast.rows 
            if any(k in row[1] for k in FAST_CLEANUP_SOURCES)
        ]
        links_to_delete.extend(fast_links)

        # ==========================================
        # 🗑️ 級別二：過期常規深度文章 (超過 180 天 且 未收藏)
        # ==========================================
        print("🔍 正在掃描過期的深度長文 (180天門檻)...")
        res_normal = db.execute("SELECT Link, Source FROM articles WHERE is_bookmarked = 0 AND SortDate < ?", [six_months_ago])
        
        normal_links = [
            row[0] for row in res_normal.rows 
            # 必須「不包含」永久保護名單，也「不包含」快訊名單 (因為快訊已經處理過了)
            if not any(k in row[1] for k in PROTECTED_SOURCES + FAST_CLEANUP_SOURCES)
        ]
        links_to_delete.extend(normal_links)

        # ==========================================
        # 🚀 執行批次精準抹除
        # ==========================================
        if links_to_delete:
            links_to_delete = list(set(links_to_delete)) # 去除重複項
            print(f"🗑️ 總共發現 {len(links_to_delete)} 篇符合清理條件的文章，準備刪除...")
            
            # 將刪除任務分批，避免單次 SQL 語句過長 (SQLite 的 IN 語句參數有上限)
            chunk_size = 50
            for i in range(0, len(links_to_delete), chunk_size):
                chunk = links_to_delete[i:i + chunk_size]
                
                # 動態產生對應數量的問號佔位符，例如: (?, ?, ?)
                placeholders = ','.join(['?'] * len(chunk))
                sql = f"DELETE FROM articles WHERE Link IN ({placeholders})"
                
                db.execute(sql, chunk)
                
            print("✅ 大掃除完成，成功釋放 Turso 資料庫空間！")
        else:
            print("✨ 檢查完畢，目前資料庫內沒有任何過期文章需要清理。")
            
    except Exception as e:
        print(f"❌ 清理過程中發生錯誤: {e}")

if __name__ == "__main__":
    clean_up_old_articles()
