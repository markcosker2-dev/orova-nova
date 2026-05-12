import sqlite3
import os

db_path = r'c:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\openclaw_instance\app\orova.db'
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM leads LIMIT 10")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
        if not rows:
            print("Leads table is empty.")
    except Exception as e:
        print(f"Error reading leads: {e}")
    conn.close()
