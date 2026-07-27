import sqlite3

conn = sqlite3.connect('afid.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("SQLite Tables:")
for row in tables:
    print(f"  - {row[0]}")
conn.close()