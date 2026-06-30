import sqlite3
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from serin.memory.qdrant import SQLiteBM25Index

def test_fix():
    db_path = "test_fix_fts.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    index = SQLiteBM25Index(db_path)
    index.add_document("doc1", "This is a test document.", "user1", "channel1")
    
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
    
    print("Testing queries with SQLiteBM25Index...")
    
    for q in queries:
        try:
            results = index.search(q)
            print(f"Query '{q}': Success ({len(results)} results)")
        except Exception as e:
            print(f"Query '{q}': FAILED - {e}")
            
    if os.path.exists(db_path):
        os.remove(db_path)
        if os.path.exists(db_path + "-wal"):
            os.remove(db_path + "-wal")
        if os.path.exists(db_path + "-shm"):
            os.remove(db_path + "-shm")

if __name__ == "__main__":
    test_fix()
