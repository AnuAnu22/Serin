import sqlite3
import os

def test_fts5_syntax():
    db_path = "test_fts.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE VIRTUAL TABLE documents_fts USING fts5(text)")
    conn.execute("INSERT INTO documents_fts (text) VALUES ('This is a test document.')")
    conn.commit()
    
    queries = [
        "test",
        "test.",
        "test...",
        "What file are you talking about?...",
        "Dougdoug is bald.",
        '"test"',
        "test:test",
        "It's a screenshot"
    ]
    
    print(f"Testing queries on {sqlite3.sqlite_version}...")
    
    for q in queries:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents_fts WHERE documents_fts MATCH ?", (q,))
            results = cursor.fetchall()
            print(f"Query '{q}': Success ({len(results)} results)")
        except sqlite3.OperationalError as e:
            print(f"Query '{q}': FAILED - {e}")
            
    conn.close()
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    test_fts5_syntax()
