"""Belief Store — conclusions inferred from facts with state machine.

State machine:
  PENDING    → first evidence arrives
  SUPPORTED  → evidence supports, no strong counter-evidence
  CONTESTED  → contradicting evidence found
  SUPERSEDED → overwhelming counter-evidence, original retracted
  UNKNOWN    → only claims exist, no supporting evidence

Confidence is computed from the evidence/claim ratio using Bayesian update.
"""

import json
import uuid
from datetime import datetime

from serin.logger import logger

_SQL_TEMPLATE_BELIEF_SEARCH = """
    SELECT * FROM beliefs
    WHERE is_active = 1 AND ({like_clauses})
    ORDER BY confidence DESC
    LIMIT ?
"""


def _build_search_query(template: str, **kwargs: str) -> str:
    return template.format(**kwargs)


class BeliefStore:
    """SQLite-backed belief store with state machine and Bayesian confidence."""

    def __init__(self, conn):
        self.conn = conn

    # ── CRUD ────────────────────────────────────────────────────────────────

    def add_or_update_belief(self, content: str, category: str = 'inference',
                             confidence: float = 0.5,
                             supporting_fact_ids: list[str] | None = None,
                             contradicting_fact_ids: list[str] | None = None,
                             evidence_count: int = 1,
                             claim_count: int = 0) -> str:
        """Store or update a belief (a conclusion inferred from facts)."""
        now = datetime.now().isoformat()
        cursor = self.conn.cursor()

        supporting_ids = json.dumps(supporting_fact_ids or [])
        contradicting_ids = json.dumps(contradicting_fact_ids or [])

        # Check existing belief with same content
        existing = cursor.execute("""
            SELECT id, confidence, evidence_count, claim_count, state,
                   last_contradicted_at
            FROM beliefs
            WHERE content = ? AND is_active = 1
        """, (content,)).fetchone()

        if existing:
            belief_id = existing[0]
            old_conf = existing[1]
            old_evidence = existing[2]
            old_claims = existing[3]
            old_state = existing[4]
            old_contradicted_at = existing[5] or ''

            total_evidence = old_evidence + evidence_count
            total_claims = old_claims + claim_count
            total = total_evidence + total_claims

            # Determine new state
            new_state = old_state
            last_contradicted_at = old_contradicted_at
            resolved_at = ''

            has_new_contradiction = (
                claim_count > evidence_count and old_state in ('PENDING', 'SUPPORTED')
            )
            if has_new_contradiction:
                new_state = 'CONTESTED'
                last_contradicted_at = now
            elif claim_count > evidence_count * 2:
                new_state = 'SUPERSEDED'
                resolved_at = now
            elif old_state == 'CONTESTED' and evidence_count > claim_count:
                new_state = 'SUPPORTED'
                resolved_at = now
            elif old_state in ('PENDING', '') and total_evidence >= 1:
                new_state = 'SUPPORTED'
            elif total_evidence == 0 and total_claims > 0:
                new_state = 'UNKNOWN'

            # Compute confidence
            evidence_ratio = total_evidence / max(total, 1)
            new_conf = 0.3 + 0.7 * evidence_ratio

            cursor.execute("""
                UPDATE beliefs
                SET state = ?, confidence = ?, evidence_count = ?,
                    claim_count = ?,
                    supporting_fact_ids = ?,
                    contradicting_fact_ids = ?,
                    last_contradicted_at = ?,
                    contradiction_resolved_at = ?,
                    updated_at = ?
                WHERE id = ?
            """, (new_state, new_conf, total_evidence, total_claims,
                  supporting_ids, contradicting_ids,
                  last_contradicted_at, resolved_at, now, belief_id))
            logger.debug(
                f"Belief updated: [{new_state}] {content[:60]}... "
                f"conf {old_conf:.2f} \u2192 {new_conf:.2f} "
                f"ev {total_evidence} cl {total_claims}"
            )
        else:
            belief_id = str(uuid.uuid4())

            initial_state = 'PENDING'
            if evidence_count >= 1 and claim_count == 0:
                initial_state = 'SUPPORTED'
            elif evidence_count == 0 and claim_count > 0:
                initial_state = 'UNKNOWN'

            cursor.execute("""
                INSERT INTO beliefs (id, content, category, state, confidence,
                                     supporting_fact_ids, contradicting_fact_ids,
                                     evidence_count, claim_count,
                                     timestamp, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (belief_id, content, category, initial_state, confidence,
                  supporting_ids, contradicting_ids,
                  evidence_count, claim_count, now, now))
            logger.debug(
                f"Belief created: [{initial_state}] {content[:60]}... "
                f"conf {confidence:.2f}"
            )

        self.conn.commit()
        return belief_id

    # ── Inference ───────────────────────────────────────────────────────────

    def infer_beliefs_from_facts(self, query: str = '') -> list[dict]:
        """Scan active facts and infer/update beliefs with state."""
        cursor = self.conn.cursor()
        facts = cursor.execute("""
            SELECT * FROM facts
            WHERE is_active = 1
            ORDER BY confidence DESC
            LIMIT 50
        """).fetchall()

        fact_rows = [dict(f) for f in facts]

        board_facts = [f for f in fact_rows if f['category'] == 'board_state']
        game_facts = [f for f in fact_rows if f['category'] == 'game_result']
        claim_facts = [f for f in fact_rows if f['category'] == 'speech_claim'
                       or f['category'].endswith('_claim')]

        beliefs = []
        all_win_evidence = board_facts + game_facts
        for bf in all_win_evidence:
            if not any(kw in bf['content'].lower()
                       for kw in ['4', 'win', 'row', 'diagonal']):
                continue

            evidence_conf = bf['confidence']
            supporting_ids = [bf['id']]
            contradicting_ids = []
            claim_count = 0

            for cf in claim_facts:
                if 'won' in cf['content'].lower() or 'win' in cf['content'].lower():
                    if cf['source_type'] == 'user_claim':
                        contradicting_ids.append(cf['id'])
                        claim_count += 1

            total = len(supporting_ids) + claim_count
            evidence_ratio = len(supporting_ids) / max(total, 1)
            belief_conf = 0.3 + 0.7 * (
                evidence_conf * (1 + len(supporting_ids)) /
                (1 + len(supporting_ids) + claim_count)
            )

            if claim_count == 0:
                state = 'SUPPORTED'
            elif evidence_ratio >= 0.66:
                state = 'SUPPORTED'
            elif evidence_ratio >= 0.33:
                state = 'CONTESTED'
            else:
                state = 'SUPERSEDED'

            belief_content = "Evidence suggests a win condition was met"
            beliefs.append({
                'content': belief_content,
                'state': state,
                'confidence': belief_conf,
                'category': 'game_outcome',
                'supporting_fact_ids': supporting_ids,
                'contradicting_fact_ids': contradicting_ids,
                'evidence_count': len(supporting_ids),
                'claim_count': claim_count,
            })

        return beliefs

    # ── Retrieval ───────────────────────────────────────────────────────────

    def get_relevant_beliefs(self, query: str, limit: int = 3) -> list[dict]:
        """Retrieve active beliefs relevant to a query."""
        cursor = self.conn.cursor()
        keywords = [w.lower() for w in query.split()
                    if len(w) > 3 and w.isalpha()]
        if not keywords:
            cursor.execute("""
                SELECT * FROM beliefs
                WHERE is_active = 1
                ORDER BY confidence DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

        like_clauses = ' OR '.join('content LIKE ?' for _ in keywords)
        like_params = [f'%{kw}%' for kw in keywords]

        query = _build_search_query(_SQL_TEMPLATE_BELIEF_SEARCH, like_clauses=like_clauses)
        cursor.execute(query, (*like_params, limit))

        return [dict(row) for row in cursor.fetchall()]
