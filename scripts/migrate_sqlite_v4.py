import sqlite3
import os

DB_PATH = "logs/usage_stats.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print("DB file not found, skipping migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        # Check if column exists
        cursor = conn.execute("PRAGMA table_info(llm_usage)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "session_id" not in columns:
            print("Adding session_id column to llm_usage table...")
            conn.execute("ALTER TABLE llm_usage ADD COLUMN session_id TEXT DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_session ON llm_usage(session_id)")
            conn.commit()
            print("✅ Migration successful.")
        else:
            print("session_id column already exists.")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
