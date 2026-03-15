import sqlite3

conn = sqlite3.connect("database.db")

conn.execute("""
CREATE TABLE expenses(
id INTEGER PRIMARY KEY AUTOINCREMENT,
amount REAL,
category TEXT,
note TEXT,
date TEXT
)
""")



conn.close()