import sqlite3

# Database connect
conn = sqlite3.connect("turnalyze.db")

cursor = conn.cursor()

# Create reports table
cursor.execute("""
CREATE TABLE IF NOT EXISTS reports (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    filename TEXT,

    upload_date TEXT,

    pages INTEGER,

    words INTEGER,

    ai_score INTEGER,

    human_score INTEGER,

    status TEXT,

    pdf_path TEXT

)
""")

conn.commit()

conn.close()

print("Database and reports table created successfully.")