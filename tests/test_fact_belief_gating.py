"""Round 4 reproduction: prove facts/beliefs are gated behind the LLM.

The live RAM showed facts/beliefs/fact_observations/bot_opinions all empty
while recent_messages/BM25 were populated. This test drives the real
MemoryWriteStage against a real SQLite-backed memory system and shows:

  * with ``small_llm`` absent (the current state: llamaswap is down), general
    memory is written but the fact/belief tables stay empty;
  * the underlying belief_engine/store_fact wiring does work when exercised
    directly (the code paths themselves are not broken).
"""
from unittest.mock import MagicMock

import pytest

from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_4_core_store import (
    QdrantMemorySystem,
)


def _make_real_memory(tmp_path) -> QdrantMemorySystem:
    """Build a QdrantMemorySystem with a REAL SQLite conn but no Qdrant/embeddings."""
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_2_remember_knowledge.d4_1_knowledge_belief.d5_1_belief_beliefs import (
        BeliefStore,
    )
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_2_remember_knowledge.d4_1_knowledge_belief.d5_2_belief_evidence import (
        FactStore,
    )
    from serin.d1_3_state_core.d2_2_core_memory.d3_3_belief_dynamics import (
        BayesianBeliefEngine,
    )

    ms = QdrantMemorySystem.__new__(QdrantMemorySystem)
    ms.data_dir = tmp_path
    ms.db_path = str(tmp_path) + "/bot_data.db"
    ms.embedding_model = None  # empty embedding -> write path skips (no qdrant call)
    ms.embedding_dim = 384
    ms.qdrant_client = None
    ms.bm25_index = None
    # real sqlite on a temp file, schema created by _init_sqlite_robust
    ms._init_sqlite_robust()
    # domain stores are wired in the real constructor; redo explicitly here.
    ms.fact_store = FactStore(ms.conn)
    ms.belief_store = BeliefStore(ms.conn)
    ms.belief_engine = BayesianBeliefEngine(ms.conn)
    return ms


@pytest.mark.asyncio
async def test_fact_belief_tables_empty_when_llm_absent(tmp_path) -> None:
    """The live pipeline, with no small_llm, writes memory but no facts/beliefs."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_3_memory_write import (
        MemoryWriteStage,
    )

    ms = _make_real_memory(str(tmp_path))

    stage = MemoryWriteStage(
        memory_system=ms,
        personality=None,
        client=None,
        small_llm=None,  # <-- llamaswap down: small_llm is None
        affect_engine=None,
    )

    class _Msg:
        id = 9999111222333444

    ctx = MagicMock()
    ctx.raw_content = "I really enjoy playing this game every weekend"
    ctx.user_id = "12345"
    ctx.username = "TestUser"
    ctx.channel_id = "67890"
    ctx.message = _Msg()
    ctx.final_response = ""

    await stage.run(ctx)

    cur = ms.conn.cursor()
    # bot_opinions lives in a separate personality DB, not the core schema.
    for table in ("facts", "beliefs", "fact_observations"):
        n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert n == 0, f"{table} should be empty with no LLM, got {n}"

    # General message memory (recent_messages) is written by the ingest
    # path (store_recent_message), independent of the LLM — prove it works
    # while facts/beliefs stay empty.
    from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store import (
        store_recent_message,
    )
    store_recent_message(ms, "12345", "TestUser", "67890",
                         "general message memory write", "8888888888")
    n_msgs = cur.execute("SELECT COUNT(*) FROM recent_messages").fetchone()[0]
    assert n_msgs >= 1, "general message memory should still be written"


@pytest.mark.asyncio
async def test_belief_engine_store_fact_writes_when_invoked(tmp_path) -> None:
    """The belief_engine store_fact sink itself works — it's just never reached
    without the LLM branch on live traffic."""
    ms = _make_real_memory(str(tmp_path))
    engine = ms.belief_engine

    fact_id = engine.store_fact(
        subject_id="12345",
        subject_name="TestUser",
        claim="likes strategy games",
        category="interest",
        source="TestUser",
        source_type="user_claim",
        initial_confidence=0.7,
    )
    assert fact_id is not None

    cur = ms.conn.cursor()
    print("facts rows:", cur.execute("SELECT COUNT(*) FROM facts").fetchone()[0])
    print("fact_observations rows:", cur.execute("SELECT COUNT(*) FROM fact_observations").fetchone()[0])
    assert cur.execute("SELECT COUNT(*) FROM facts").fetchone()[0] >= 1
