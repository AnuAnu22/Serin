"""SQLiteBM25Index — BM25 full-text search."""
import sqlite3


class SQLiteBM25Index:
    """SQLite-based BM25 index for keyword search"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._setup_schema()

    def _setup_schema(self):
        """Setup BM25 index schema"""
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                id UNINDEXED,
                text,
                person_id UNINDEXED,
                channel_id UNINDEXED
            )
        """)

        self.conn.commit()

    def add_document(self, doc_id: str, text: str, person_id: str, channel_id: str) -> None:
        """Add document to BM25 index"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO documents_fts (id, text, person_id, channel_id)
            VALUES (?, ?, ?, ?)
        """, (doc_id, text, person_id, channel_id))

        self.conn.commit()

    def _sanitize_query(self, query: str) -> str:
        """Sanitize FTS5 query using Rust-accelerated single-pass."""
        try:
            import serin_core
            return serin_core.sanitize_fts_query(query)
        except ImportError:
            special_chars = set('+-*<>":()^~{}[]\\!?.\',')
            return ''.join(' ' if ch in special_chars else ch for ch in query).strip()

    def search(self, query: str, user_id: str | None = None, channel_id: str | None = None, limit: int = 20) -> list[dict]:
        """Search documents using BM25"""
        cursor = self.conn.cursor()

        where_conditions = []
        params = []

        if user_id:
            where_conditions.append("person_id = ?")
            params.append(user_id)

        if channel_id:
            where_conditions.append("channel_id = ?")
            params.append(channel_id)


        sanitized_query = self._sanitize_query(query)
        if not sanitized_query:
            return []

        cursor.execute("""
            SELECT id, text, person_id, channel_id,
                   bm25(documents_fts) as score
            FROM documents_fts
            WHERE documents_fts MATCH ? AND {where_clause}
            ORDER BY score
            LIMIT ?
        """, (sanitized_query, *params, limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'text': row[1],
                'person_id': row[2],
                'channel_id': row[3],
                'score': row[4]
            })

        return results

    def delete_documents(self, doc_ids: list[str]) -> None:
        """Delete documents from index"""
        cursor = self.conn.cursor()

        for doc_id in doc_ids:
            cursor.execute("DELETE FROM documents_fts WHERE id = ?", (doc_id,))

        self.conn.commit()

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

