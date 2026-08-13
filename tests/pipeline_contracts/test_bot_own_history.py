"""Contract: Serin's OWN prior reply reaches the model in a follow-up turn.

Both causes are now fixed (Task 2): ``MemoryWriteStage`` persists the bot's
reply to ``recent_messages`` (Cause 1) and ``_filter_history_messages`` keeps
the bot's turns instead of dropping them (Cause 2). This is the permanent
regression guard — it must stay green.

1. Cause 1 (SQLite write gap): the user's incoming message is stored to
   ``recent_messages`` by the ingest path, but the bot's reply was only ever
   written to Qdrant. Now ``MemoryWriteStage`` also calls ``store_recent_message``
   for ``ctx.final_response``.

2. Cause 2 (filter): ``PromptAssemblyStage._filter_history_messages`` used to
   drop the bot's turns; it now keeps them as ordinary context.

This test models the REAL two-message lifecycle with a single persistent fake
store, exactly as production persistence behaves:

  Phase 1: a user message arrives, the bot replies (final_response = R1).
           We replicate core_manager's user-message storage so the ONLY
           variable is whether the bot's R1 was also persisted.
  Phase 2: a follow-up message arrives. Its context is whatever was persisted
           in phase 1. We assert R1 is present in the messages that reach the
           model.
"""
from __future__ import annotations

from tools.pipeline_inspector.scenario import Scenario, _Snap

USER_ID = "1234"
USERNAME = "Sam"
M1 = "hey what about the cake we got"
R1 = "the cake was definitely chocolate, not vanilla"
M2 = "wait, what kind of cake did you say it was again?"


def _stored_shape(memory) -> list[dict[str, str]]:
    """Rebuild the recent_messages context the way production persistence would.

    Production ``get_recent_conversation`` returns rows with
    ``user_id/username/content/timestamp`` — exactly the fields
    ``store_recent_message`` recorded.
    """
    return [
        {
            "user_id": w["user_id"],
            "username": w["username"],
            "content": w["content"],
        }
        for w in memory.recent_writes
    ]


async def test_bot_own_prior_reply_reaches_model(run_contract) -> None:
    # ---- Phase 1: user speaks, bot replies --------------------------------
    scenario1 = Scenario(
        content=M1,
        user_id=USER_ID,
        username=USERNAME,
        affect=_Snap(valence=0.5, familiarity=0.5),
    )
    result1 = await run_contract(scenario1, force_reply=True)
    assert result1.ctx.final_response, "bot did not produce a reply in phase 1"
    bot_reply = result1.ctx.final_response

    memory = result1.memory
    # Replicate core_manager's user-message persistence (production does this
    # for the incoming user message, NOT for the bot's reply).
    memory.store_recent_message(
        user_id=USER_ID, username=USERNAME, channel_id="inspector",
        content=M1, message_id="m1",
    )

    # ---- Checkpoint (Cause 1): the bot's reply must have been persisted ----
    stored_replies = [w for w in memory.recent_writes if w["content"] == bot_reply]
    assert stored_replies, (
        "Cause 1: bot's reply was NEVER written to recent_messages. "
        "MemoryWriteStage must call store_recent_message for ctx.final_response. "
        f"recent_writes={memory.recent_writes!r}"
    )
    # With no live client in the harness, the fallback bot user id is "serin".
    assert stored_replies[0]["user_id"] == "serin", (
        f"bot reply stored under unexpected user_id: {stored_replies[0]['user_id']!r}"
    )

    # ---- Phase 2: follow-up message, context = whatever was persisted -----
    scenario2 = Scenario(
        content=M2,
        user_id=USER_ID,
        username=USERNAME,
        affect=_Snap(valence=0.5, familiarity=0.5),
        recent_messages=_stored_shape(memory),
    )
    result2 = await run_contract(scenario2, force_reply=True)
    assert result2.ctx.halt_reason == "", (
        f"follow-up unexpectedly halted: {result2.ctx.halt_reason!r}"
    )

    # ---- Checkpoint (end-to-end): the bot's R1 is in what reaches model ----
    joined = "\n".join(m["content"] for m in result2.built_messages)
    assert bot_reply in joined, (
        "Serin's own prior reply is MISSING from what reaches the model on the "
        "next turn. Root cause: it was never persisted to recent_messages "
        "(Cause 1 write gap), so phase-2 context had nothing to surface."
    )
