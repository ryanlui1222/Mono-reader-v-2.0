import os
import pandas as pd
import libsql_client
from datetime import datetime

def run_backup():
    print("🚀 開始執行 Turso 資料庫備份...")
    
    # 確保環境變數已設定 (本機端請確保有設定 TURSO_DATABASE_URL 與 TURSO_AUTH_TOKEN)
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if not url or not token:
        print("❌ 錯誤：找不到 Turso 環境變數。")
        return

    try:
        db = libsql_client.create_client_sync(url=url, auth_token=token)
        
        # 1. 抓取資料庫中所有的資料表名稱
        tables_res = db.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in tables_res.rows if row[0] != "sqlite_sequence"]
        
        # 2. 建立當天日期的備份資料夾
        date_str = datetime.now().strftime("%Y-%m-%d")
        backup_dir = f"backup_{date_str}"
        os.makedirs(backup_dir, exist_ok=True)
        
        # 3. 逐一將資料表匯出為 CSV
        for table in tables:
            res = db.execute(f"SELECT * FROM {table}")
            if res.rows:
                columns = res.columns
                data = [list(row) for row in res.rows]
                df = pd.DataFrame(data, columns=columns)
                
                file_path = os.path.join(backup_dir, f"{table}.csv")
                df.to_csv(file_path, index=False, encoding='utf-8-sig')
                print(f"✅ 成功備份資料表: {table} ({len(df)} 筆記錄)")
            else:
                print(f"⚠️ 資料表 {table} 為空，略過備份。")
                
        print(f"🎉 備份完成！所有檔案已儲存於 {backup_dir}/ 資料夾中。")
        
    except Exception as e:
        print(f"❌ 備份過程發生錯誤: {e}")
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    run_backup()
