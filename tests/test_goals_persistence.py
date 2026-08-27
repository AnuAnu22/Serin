"""C4 persistence tests: boot restore + shutdown flush (mirror dynamics)."""
import sqlite3
from typing import Any

from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_6_goal_storage import (
    d6_1_goals_store as gs,
)
from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_3_schema_store import (
    init_sqlite_schema,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_4_goals_engine import (
    FLUSH_INTERVAL_S,
    GoalsEngine,
)


def _store() -> Any:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_sqlite_schema(conn, conn.cursor())

    class MockStore:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self.conn = connection

    return MockStore(conn)


def test_restore_loads_live_goals_and_skips_terminal() -> None:
    store = _store()
    gs.create_goal(store, 'live one', 0.5, status='ACTIVE')
    gs.create_goal(store, 'done one', 0.5, status='ACHIEVED')
    eng = GoalsEngine(store)
    n = eng.restore_from_store()
    assert n == 1  # terminal ACHIEVED excluded
    assert len(eng._goals) == 1
    assert 1 in eng._goals


def test_restore_never_raises_on_broken_store() -> None:
    class Broken:
        conn = None
    eng = GoalsEngine(Broken())
    assert eng.restore_from_store() == 0
    assert eng._goals == {}


def test_flush_is_throttled_unless_forced() -> None:
    import time
    store = _store()
    gs.create_goal(store, 'flush probe', 0.5, status='ACTIVE')
    eng = GoalsEngine(store)
    eng.restore_from_store()
    # Simulate a just-completed flush, then a non-forced call inside
    # the throttle window must be skipped (returns 0, no commit).
    eng._last_flush = time.time()
    assert eng.flush_to_store() == 0
    # Forced flush commits and returns the live count regardless.
    saved = eng.flush_to_store(force=True)
    assert saved == 1


def test_flush_never_raises_on_broken_store() -> None:
    class Broken:
        conn = None
    eng = GoalsEngine(Broken())
    eng._last_flush = 0.0
    assert eng.flush_to_store(force=True) == 0


def test_flush_interval_constant_positive() -> None:
    assert FLUSH_INTERVAL_S > 0
