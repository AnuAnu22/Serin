"""Goals self-play eval harness (C6): assert the engine actually forms,
pursues, decays, and drops through the REAL maintenance + decision edges.

No live LLM: a scripted ModelInterface stand-in returns queued formation JSON,
so the loop is deterministic and CI-runnable. The harness drives:
- BackgroundProcessor._run_goals_maintenance (review -> promote -> form), and
- ResponseDecisionStage._goal_salience_bonus (the pursuit weight edge).

Doctrine: goals are assertable through real edge behavior, not unit mocks of
the engine internals. See wiki/entities/goals_engine.md (C6).

# --- Imports ---
"""
from __future__ import annotations

import asyncio
import sqlite3
import types
from typing import Any

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_1_decision_temporal import (
    ResponseDecisionStage,
)
from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage import (
    d6_1_goals_store as gs,
)
from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_3_schema_store import (
    init_sqlite_schema,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_4_goals_engine import (
    GoalsEngine,
)
from serin.d1_5_ops_tooling.d2_2_tooling_background.d5_1_tooling_background import (
    BackgroundProcessor,
)

# --- Fakes ---


class FakeExtractorLLM:
    """Scripted ModelInterface stand-in for background formation.

    Returns queued formation JSON via chat_completion, or the empty-goal
    escape hatch, simulating the supporting LLM without a live model.
    """

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.is_connected: bool = True
        self.calls: list[dict[str, Any]] = []

    async def chat_completion(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        self.calls.append({'messages': messages, **kwargs})
        if self._replies:
            return self._replies.pop(0)
        return '{"statement": "", "salience": 0.0}'


class FakeMemorySystem:
    """Minimal memory_system exposing a real SQLite store + schema."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_sqlite_schema(self.conn, self.conn.cursor())
        self.affect_engine = None

    def seed_recent(self, lines: list[str], channel: str = 'c1', user_id: str = 'u1', username: str = 'alice', prefix: str = 'm') -> None:
        cur = self.conn.cursor()
        for i, text in enumerate(lines):
            cur.execute(
                'INSERT INTO recent_messages (message_id, user_id, username, channel_id, content, timestamp) '
                'VALUES (?,?,?,?,?, datetime(\'now\', ? || \' seconds\'))',
                (f'{prefix}{i}', user_id, username, channel, text, f'-{i}'),
            )
        self.conn.commit()

    def clear_recent(self) -> None:
        self.conn.execute('DELETE FROM recent_messages')
        self.conn.commit()


def _make_processor(memory: FakeMemorySystem, llm: FakeExtractorLLM) -> Any:
    """Wire a real BackgroundProcessor with a scripted LLM + goals engine."""
    proc = BackgroundProcessor(memory)
    proc.goals_engine = GoalsEngine(memory)
    proc.extractor_llm = llm
    return proc


def _make_ctx(raw: str) -> Any:
    """Minimal MessageContext (mirrors tests/test_goals_pursuit.py)."""
    msg = types.SimpleNamespace(
        author=types.SimpleNamespace(id=12345, name='TestUser'),
        guild=types.SimpleNamespace(id=11111, me=object()),
        mentions=[], content=raw,
    )
    return MessageContext(
        message=msg, user_id='12345', username='TestUser',
        channel_id='67890', guild_id='11111', raw_content=raw,
    )


# --- Self-play: formation through the real maintenance edge ---


def test_selfplay_forms_goal_from_conversation() -> None:
    """A forming LLM reply yields a real goal row via _run_goals_maintenance."""
    mem = FakeMemorySystem()
    mem.seed_recent([
        'user: i keep losing my ssh configs between machines',
        'user: there should be a single source of truth for dotfiles',
        'user: every reinstall i redo the same setup from memory',
        'user: a managed dotfiles repo would save me hours',
        'user: i always forget which tools i had installed',
    ])
    llm = FakeExtractorLLM(['{"statement": "keep a managed dotfiles repo", "salience": 0.7}'])
    proc = _make_processor(mem, llm)
    asyncio.run(proc._run_goals_maintenance())
    rows = gs.get_active_goals(mem, min_salience=0.0, limit=50)
    assert len(rows) == 1
    assert rows[0]['statement'] == 'keep a managed dotfiles repo'
    assert float(rows[0]['salience']) == 0.7
    assert rows[0]['status'] in ('FORMING', 'ACTIVE')
    assert 'maintenance:formation' in str(rows[0]['origin_provenance'])


def test_selfplay_declines_when_llm_returns_empty() -> None:
    """The empty-goal escape hatch forms nothing - zero rows."""
    mem = FakeMemorySystem()
    mem.seed_recent(['a', 'b', 'c', 'd', 'e'] * 2)
    llm = FakeExtractorLLM([])  # replies default to the escape hatch
    proc = _make_processor(mem, llm)
    asyncio.run(proc._run_goals_maintenance())
    assert gs.count_goals_by_status(mem) == {}


def test_selfplay_forming_then_active_after_review() -> None:
    """A FORMING goal is stamped by review, then promote_ready promotes it."""
    mem = FakeMemorySystem()
    gid = gs.create_goal(mem, 'finish the changelog tool', 0.6, status='FORMING')
    engine = GoalsEngine(mem)
    # A review stamps last_reviewed_at (the gate promote_ready checks).
    engine.review_due(older_than_s=0)
    promoted = engine.promote_ready()  # FORMING survived its first window
    assert promoted == 1
    row = gs.get_active_goals(mem, min_salience=0.0, limit=50)[0]
    assert int(row['id']) == gid
    assert row['status'] == 'ACTIVE'


def test_selfplay_pursuit_weight_is_deterministic_and_scales() -> None:
    """ResponseDecisionStage._goal_salience_bonus lifts engagement for
    actively-pursued goals: positive, salience-weighted, deterministic."""
    mem = FakeMemorySystem()
    engine = GoalsEngine(mem)
    gs.create_goal(mem, 'ship the docs site', 0.8, status='ACTIVE')
    stage = ResponseDecisionStage(goals_engine=engine)
    goals = engine.pursuit_snapshot(limit=3)
    bonus = stage._goal_salience_bonus(goals)
    assert bonus > 0  # pursuit raises engagement
    # Weighted by salience: a second above-floor goal lifts more.
    gs.create_goal(mem, 'second live drive', 0.50, status='ACTIVE')
    goals2 = engine.pursuit_snapshot(limit=3)
    # bonus is monotonic in total salience -> more goals/salience = more bonus
    assert stage._goal_salience_bonus(goals2) > bonus
    # Deterministic: same inputs => same output (no RNG anywhere).
    assert stage._goal_salience_bonus(goals2) == stage._goal_salience_bonus(list(goals2))


def test_selfplay_decay_and_drop_over_reviews() -> None:
    """Salience decays and a floor-dead goal auto-drops across forced reviews."""
    mem = FakeMemorySystem()
    gs.create_goal(mem, 'review the configs', 0.20, status='ACTIVE')
    engine = GoalsEngine(mem)
    for _ in range(6):
        engine.review_due(older_than_s=0)
    counts = gs.count_goals_by_status(mem)
    # 0.20 - 6*0.03 = 0.02 < 0.05 floor -> DROPPED, no longer ACTIVE.
    assert counts.get('ACTIVE', 0) == 0
    assert counts.get('DROPPED', 0) >= 1


def test_selfplay_goals_remain_separated_per_user() -> None:
    """Two users form goals from their own lines; they never cross-contaminate.

    Formation now groups recent_messages by user_id, and pursuit_snapshot is
    user-scoped, so Alice's goals stay Alice's and Bob's stay Bob's (C7).
    """
    mem = FakeMemorySystem()
    mem.seed_recent([
        'i want to learn rust this year',
        'a side project in rust would be fun',
        'i should read the rust book',
        'rust async is confusing but interesting',
        'maybe build a rust cli tool',
    ], user_id='u_alice', username='alice', prefix='a')
    mem.seed_recent([
        'i want to get better at watercolour',
        'a daily sketch habit sounds nice',
        'i should buy better brushes',
        'watercolour landscapes relax me',
        'maybe join a painting class',
    ], user_id='u_bob', username='bob', prefix='b')
    llm = FakeExtractorLLM([
        '{"statement": "learn rust", "salience": 0.8}',
        '{"statement": "practice watercolour", "salience": 0.7}',
    ])
    proc = _make_processor(mem, llm)
    asyncio.run(proc._run_goals_maintenance())
    alice = gs.get_active_goals(mem, min_salience=0.0, limit=50, user_id='u_alice')
    bob = gs.get_active_goals(mem, min_salience=0.0, limit=50, user_id='u_bob')
    assert len(alice) == 1 and 'learn rust' in str(alice[0]['statement'])
    assert len(bob) == 1 and 'watercolour' in str(bob[0]['statement'])
    assert all('watercolour' not in str(r['statement']) for r in alice)
    assert all('learn rust' not in str(r['statement']) for r in bob)
    engine = GoalsEngine(mem)
    assert len(engine.pursuit_snapshot(limit=5, user_id='u_alice')) == 1
    assert len(engine.pursuit_snapshot(limit=5, user_id='u_bob')) == 1
    assert len(engine.pursuit_snapshot(limit=50)) == 2
