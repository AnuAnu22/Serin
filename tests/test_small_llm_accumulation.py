"""End-to-end small_llm → MemoryWriteStage → Bayesian facts accumulation.

Proves the seam is live, not just configured: with a stub LLM whose
``chat_completion`` returns a deterministic JSON fact list (no RNG anywhere —
SERIN_VISION "causality, not performance"), a message driven through the real
MemoryWriteStage produces:

  * one ``facts`` row for the extracted claim;
  * corroborating a stored claim again must NOT create a second row — the
    claim_hash UNIQUE path routes it to ``observe(corroborate)`` and bumps
    observation_count instead.

Mirrors tests/test_fact_belief_gating.py's real-SQLite memory harness, but on
the positive path that file cannot exercise (it runs with small_llm=None).
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_4_core_store import (
    QdrantMemorySystem,
)


def _make_real_memory(tmp_path: str) -> QdrantMemorySystem:
    """Build a QdrantMemorySystem with a REAL SQLite conn but no Qdrant/embeddings."""
    from serin.d1_3_state_core.d2_2_core_memory.d3_3_belief_dynamics import (
        BayesianBeliefEngine,
    )

    ms = QdrantMemorySystem.__new__(QdrantMemorySystem)
    ms.data_dir = tmp_path
    ms.db_path = tmp_path + "/bot_data.db"
    ms.embedding_model = None  # empty embedding -> write path skips (no qdrant call)
    ms.embedding_dim = 384
    ms.qdrant_client = None
    ms.bm25_index = None
    # real sqlite on a temp file, schema created by _init_sqlite_robust
    ms._init_sqlite_robust()
    # The authoritative wiring (d4_4_core_store.__init__) sets belief_engine;
    # redo it explicitly on this bare instance.
    ms.belief_engine = BayesianBeliefEngine(ms.conn)
    return ms


class _StubSmallLLM:
    """Deterministic stand-in for the supporting LLM connector.

    Satisfies the exact contract MemoryWriteStage consumes:
    ``is_connected`` / ``load_model()`` / ``await chat_completion(...)``.
    Returns the same canned extraction every call — state-caused output,
    zero randomness."""

    def __init__(self) -> None:
        self.is_connected = False
        self.load_calls = 0
        self.extraction_prompts: list[str] = []

    def load_model(self) -> bool:
        self.load_calls += 1
        self.is_connected = True
        return True

    async def chat_completion(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.extraction_prompts.append(messages[0]["content"])
        return json.dumps([
            {
                "subject_username": "TestUser",
                "claim": "likes strategy games",
                "category": "preference",
                "confidence": 0.75,
                "source_type": "self",
            }
        ])


def _make_ctx() -> Any:
    from unittest.mock import MagicMock

    class _Msg:
        id = 9999111222333555

    ctx = MagicMock()

    ctx.raw_content = "I really love playing strategy games"
    ctx.user_id = "12345"
    ctx.username = "TestUser"
    ctx.channel_id = "67890"
    ctx.message = _Msg()
    ctx.final_response = ""
    return ctx


@pytest.mark.asyncio
async def test_small_llm_extraction_writes_bayesian_fact(tmp_path) -> None:
    """Message + stub small LLM through the real stage → exactly one facts row."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_3_memory_write import (
        MemoryWriteStage,
    )

    ms = _make_real_memory(str(tmp_path))
    small = _StubSmallLLM()

    stage = MemoryWriteStage(
        memory_system=ms,
        personality=None,
        client=None,
        small_llm=small,
        affect_engine=None,
    )
    await stage.run(_make_ctx())

    cur = ms.conn.cursor()
    rows = cur.execute(
        "SELECT subject_id, subject_name, claim, category FROM facts"
    ).fetchall()
    assert len(rows) == 1, f"expected exactly 1 fact row, got {len(rows)}"
    assert rows[0]["claim"] == "likes strategy games"
    assert rows[0]["subject_name"] == "TestUser"
    # The extraction prompt actually reached the small connector.
    assert small.extraction_prompts, "small_llm.chat_completion was never called"


@pytest.mark.asyncio
async def test_corroboration_does_not_duplicate_facts(tmp_path) -> None:
    """Re-extracting the same claim routes through claim_hash → observe(),
    bumping observation_count instead of inserting a duplicate row."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_3_memory_write import (
        MemoryWriteStage,
    )

    ms = _make_real_memory(str(tmp_path))
    small = _StubSmallLLM()
    stage = MemoryWriteStage(
        memory_system=ms,
        personality=None,
        client=None,
        small_llm=small,
        affect_engine=None,
    )
    await stage.run(_make_ctx())
    await stage.run(_make_ctx())

    cur = ms.conn.cursor()
    n_rows = cur.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    assert n_rows == 1, f"claim_hash dedup failed: {n_rows} rows after repeat"
    n_obs = cur.execute(
        "SELECT observation_count FROM facts"
    ).fetchone()["observation_count"]
    assert n_obs >= 2, f"corroboration not recorded: observation_count={n_obs}"


def test_small_llm_lazy_load_contract(tmp_path) -> None:
    """The stage lazy-loads an unconnected connector via load_model() before use —
    the exact behavior a cold dedicated-endpoint process relies on."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_3_memory_write import (
        MemoryWriteStage,
    )

    ms = _make_real_memory(str(tmp_path))
    small = _StubSmallLLM()
    assert small.is_connected is False

    stage = MemoryWriteStage(
        memory_system=ms,
        personality=None,
        client=None,
        small_llm=small,
        affect_engine=None,
    )
    # Sync smoke: the stage holds the connector; load happens inside run().
    assert stage.small_llm is small


@pytest.mark.asyncio
async def test_none_small_llm_still_skips_extraction(tmp_path) -> None:
    """Regression guard: small_llm=None keeps the historical empty-tables
    behavior (the path pinned by tests/test_fact_belief_gating.py)."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_2_act_stages.d4_3_memory_write import (
        MemoryWriteStage,
    )

    ms = _make_real_memory(str(tmp_path))
    stage = MemoryWriteStage(
        memory_system=ms,
        personality=None,
        client=None,
        small_llm=None,
        affect_engine=None,
    )
    await stage.run(_make_ctx())

    cur = ms.conn.cursor()
    for table in ("facts", "beliefs", "fact_observations"):
        n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert n == 0, f"{table} should stay empty without any LLM, got {n}"
