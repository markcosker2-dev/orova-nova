import sqlite3
import os

db_path = "app/data/orova_v5.db"

if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check count
cursor.execute("SELECT count(*) FROM chat_history")
count = cursor.fetchone()[0]
print(f"Current chat history count: {count}")

if count > 20:
    print("Truncating history to last 10 messages for performance...")
    # Keep only the last 10 messages
    cursor.execute("""
        DELETE FROM chat_history 
        WHERE id NOT IN (
            SELECT id FROM chat_history 
            ORDER BY id DESC LIMIT 10
        )
    """)
    conn.commit()
    print("Truncation complete.")
else:
    print("History size is fine.")

conn.close()
