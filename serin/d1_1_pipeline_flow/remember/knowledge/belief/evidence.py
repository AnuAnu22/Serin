"""Fact Store — verifiable information extracted from messages.

Facts are small, atomic pieces of verifiable information stored in SQLite
with keyword-based retrieval. Each fact has a source_type indicating its
reliability tier and an auto-supersede mechanism for board/game state.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from serin.d1_3_state_core.logger import logger

_SQL_TEMPLATE_FACT_SEARCH = """
    SELECT f.*,
           ( {score_clause} ) as relevance
    FROM facts f
    WHERE f.is_active = 1 AND ({like_clauses})
    ORDER BY relevance DESC, f.confidence DESC, f.timestamp DESC
    LIMIT ?
"""


def _build_search_query(template: str, **kwargs: str) -> str:
    return template.format(**kwargs)


class FactStore:
    """SQLite-backed store for atomic, verifiable facts.

    Facts are independent of the conversation they came from. Source_type
    indicates reliability:
      - evidence_extracted: extracted from board/URL/code/quote (0.8-1.0)
      - user_claim: stated by a user without supporting evidence (0.1-0.3)
      - bot_assertion: stated by the bot itself (0.7-0.9)
      - verified: confirmed through multiple sources

    Auto-supersede: new board_state / game_result / reference facts
    invalidate older active facts of the same category.
    """

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    # ── CRUD ────────────────────────────────────────────────────────────────

    def add_fact(self, content: str, category: str = 'observation',
                 confidence: float = 0.5, source_message_id: str = '',
                 source_user_id: str = '', source_username: str = '',
                 source_type: str = 'user_claim') -> str:
        """Store a fact extracted from a message."""
        fact_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        cursor = self.conn.cursor()

        # Auto-supersede: later board states invalidate earlier ones
        if category in ('board_state', 'game_result', 'reference'):
            old_facts = cursor.execute("""
                SELECT id FROM facts
                WHERE is_active = 1 AND category = ? AND id != ?
                ORDER BY timestamp DESC
            """, (category, '')).fetchall()
            for row in old_facts:
                cursor.execute("""
                    UPDATE facts SET is_active = 0, superseded_by = ?,
                                    updated_at = ?
                    WHERE id = ?
                """, (fact_id, now, row[0]))
                logger.debug(
                    f"Fact superseded: [{category}] {row[0]} \u2192 {fact_id}"
                )

        cursor.execute("""
            INSERT INTO facts (id, content, category, confidence,
                               source_message_id, source_user_id, source_username,
                               source_type, timestamp, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (fact_id, content, category, confidence,
              source_message_id, source_user_id, source_username,
              source_type, now, now))
        self.conn.commit()
        logger.debug(f"Fact stored: [{category}] {content[:60]}...")
        return fact_id

    def get_active_facts(self, category: str | None = None,
                         limit: int = 10) -> list[dict[str, Any]]:
        """Retrieve active facts, optionally filtered by category."""
        cursor = self.conn.cursor()
        if category:
            cursor.execute("""
                SELECT * FROM facts
                WHERE is_active = 1 AND category = ?
                ORDER BY confidence DESC, timestamp DESC
                LIMIT ?
            """, (category, limit))
        else:
            cursor.execute("""
                SELECT * FROM facts
                WHERE is_active = 1
                ORDER BY confidence DESC, timestamp DESC
                LIMIT ?
            """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_relevant_facts(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve active facts relevant to a query using keyword overlap.

        This is intentionally simple — facts are small, atomic, and keyword
        matching works well for retrieval. Embedding-based fact retrieval
        would over-amplify semantically similar claims.
        """
        cursor = self.conn.cursor()
        keywords = [w.lower() for w in query.split()
                    if len(w) > 3 and w.isalpha()]
        if not keywords:
            return []

        # Build FTS-like keyword matching from the facts table
        like_clauses = ' OR '.join('f.content LIKE ?' for _ in keywords)
        like_params = [f'%{kw}%' for kw in keywords]
        score_clause = ' + '.join(
            "(CASE WHEN f.content LIKE ? THEN 1 ELSE 0 END)"
            for _ in keywords
        )

        query = _build_search_query(
            _SQL_TEMPLATE_FACT_SEARCH,
            score_clause=score_clause,
            like_clauses=like_clauses,
        )
        cursor.execute(query, (*like_params, *like_params, limit))

        return [dict(row) for row in cursor.fetchall()]

    def supersede_fact(self, fact_id: str, superseded_by: str = '') -> None:
        """Mark a fact as superseded (no longer active)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE facts
            SET is_active = 0, superseded_by = ?, updated_at = ?
            WHERE id = ?
        """, (superseded_by, datetime.now().isoformat(), fact_id))
        self.conn.commit()

    def deactivate_facts_by_message(self, source_message_id: str) -> None:
        """Deactivate all facts extracted from a specific message."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE facts
            SET is_active = 0, updated_at = ?
            WHERE source_message_id = ?
        """, (datetime.now().isoformat(), source_message_id))
        self.conn.commit()
