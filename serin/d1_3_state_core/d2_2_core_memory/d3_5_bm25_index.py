"""SQLiteBM25Index — BM25 full-text search."""
from __future__ import annotations

import sqlite3
from typing import Any


class SQLiteBM25Index:
    """SQLite-based BM25 index for keyword search"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._setup_schema()

    def _setup_schema(self) -> None:
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
            _sanitize: Any = getattr(serin_core, 'sanitize_fts_query')
            result: str = _sanitize(query)
            return result
        except (ImportError, AttributeError):
            special_chars = set('+-*<>":()^~{}[]\\!?.\',')
            return ''.join(' ' if ch in special_chars else ch for ch in query).strip()

    def search(self, query: str, user_id: str | None = None, channel_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Search documents using BM25"""
        cursor = self.conn.cursor()

        sanitized_query = self._sanitize_query(query)
        if not sanitized_query:
            return []

        # Build parameterized WHERE clause from fixed fragments
        conditions = ["documents_fts MATCH ?"]
        params: list[Any] = [sanitized_query]

        if user_id:
            conditions.append("person_id = ?")
            params.append(user_id)

        if channel_id:
            conditions.append("channel_id = ?")
            params.append(channel_id)

        params.append(limit)

        # Build SQL from fixed string literals only — no variable interpolation
        where_parts = ["SELECT id, text, person_id, channel_id,",
                       " bm25(documents_fts) as score",
                       " FROM documents_fts WHERE "]
        where_parts.extend(conditions)
        where_parts.append(" ORDER BY score LIMIT ?")
        sql = "".join(where_parts)
        cursor.execute(sql, params)

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

    def __del__(self) -> None:
        if hasattr(self, 'conn'):
            self.conn.close()

