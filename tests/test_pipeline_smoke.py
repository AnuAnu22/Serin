"""Pipeline smoke tests — validate core context injection and memory writing.

These tests ensure that the pipeline never silently drops context, debug data,
or memory writes. They catch the exact class of bugs introduced during refactoring
where the code compiles but runtime behavior is broken.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import MessageContext


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------

def _mock_message(content: str = "Hey Serin, who are you?"):
    msg = MagicMock()
    msg.author.id = 12345
    msg.author.display_name = "TestUser"
    msg.channel.id = 67890
    msg.guild.id = 11111
    msg.content = content
    msg.guild = MagicMock()
    msg.guild.id = 11111
    msg.guild.me = MagicMock()
    msg.guild.me.id = 99999
    msg.channel.send = AsyncMock()
    msg.reply = AsyncMock()
    return msg


def _mock_message_context(content: str = "Hey Serin, who are you?"):
    msg = _mock_message(content)
    ctx = MessageContext(
        message=msg,
        user_id="12345",
        username="TestUser",
        channel_id="67890",
        guild_id="11111",
        raw_content=content,
    )
    ctx.recent_messages = [
        {"role": "user", "content": "Hello!", "author_id": "12345"},
        {"role": "assistant", "content": "Hey there!", "author_id": "99999"},
        {"role": "user", "content": "How are you?", "author_id": "12345"},
        {"role": "assistant", "content": "I'm doing great!", "author_id": "99999"},
    ]
    ctx.system_prompt = "You are Serin. You're a real person in this Discord server."
    ctx.context_block = "User profile: TestUser likes cats."
    return ctx


def _mock_memory_system():
    ms = MagicMock()
    ms.get_user_profile.return_value = {"personality_traits": ["friendly"]}
    ms.get_relevant_facts.return_value = []
    ms.get_relevant_beliefs.return_value = []
    ms.get_user_relationships.return_value = []
    ms.get_recent_conversation.return_value = []
    ms.search_hybrid.return_value = []
    return ms


def _mock_retrieval():
    r = MagicMock()
    r.build_context.return_value = {
        "facts": [],
        "beliefs": [],
        "evidence_memories": [],
        "episode_memories": [],
        "utterance_memories": [],
        "recent_conversation": [],
        "relationships": [],
        "profiles": {},
    }
    return r


def _mock_controller():
    ctrl = MagicMock()
    ctrl.should_respond.return_value = (True, "mentioned")
    return ctrl


def _mock_personality():
    p = MagicMock()
    p.get_tone_modifier.return_value = "friendly"
    p.get_personality_context.return_value = "You are a helpful assistant."
    p.current_mood = "neutral"
    p.energy_level = 0.5
    p.sass_level = 0.5
    p.engagement = 0.5
    return p


def _mock_response_generator():
    return AsyncMock(return_value="I'm Serin, a friendly AI assistant!")


def _mock_thinking_filter():
    tf = MagicMock()
    tf.filter.return_value = "I'm Serin, a friendly AI assistant!"
    return tf


# ---------------------------------------------------------------------------
# Test 1: Context Injection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_injection_history_not_discarded():
    """Conversation history MUST be appended to built_messages, not discarded."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_3_prompt_assembly.d5_1_prompt_assembly import (
        PromptAssemblyStage,
    )

    ctx = _mock_message_context()
    stage = PromptAssemblyStage(
        mention_translator=MagicMock(),
        memory_system=_mock_memory_system(),
    )
    stage = await stage.run(ctx)

    # The system prompt + context block are at indices 0-1.
    # Conversation history MUST be appended after them.
    assert len(ctx.built_messages) > 2, (
        f"Expected > 2 messages (system + context + history), got {len(ctx.built_messages)}. "
        "Conversation history was discarded!"
    )

    # System prompt must contain persona
    system_msgs = [m for m in ctx.built_messages if m.get("role") == "system"]
    assert len(system_msgs) >= 1, "No system message in built_messages"
    assert "Serin" in system_msgs[0]["content"] or "serin" in system_msgs[0]["content"].lower(), (
        "System prompt does not contain bot persona 'Serin'"
    )

    # History messages should be present
    history_msgs = [m for m in ctx.built_messages if m.get("role") in ("user", "assistant")]
    assert len(history_msgs) > 0, (
        f"No conversation history in built_messages. Got {len(ctx.built_messages)} total messages."
    )


# ---------------------------------------------------------------------------
# Test 2: Debug Store Wiring
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_debug_store_wiring():
    """PromptAssemblyStage MUST write to the debug store, not just log."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_3_prompt_assembly.d5_1_prompt_assembly import (
        PromptAssemblyStage,
    )
    from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_6_routes.d5_3_debug_routes.d6_2_debug_routes import (
        _prompt_history,
    )

    initial_count = len(_prompt_history)

    ctx = _mock_message_context()
    stage = PromptAssemblyStage(
        mention_translator=MagicMock(),
        memory_system=_mock_memory_system(),
    )
    stage = await stage.run(ctx)

    # Exactly 1 new entry should have been appended
    assert len(_prompt_history) == initial_count + 1, (
        f"Expected 1 new debug entry (had {initial_count}, now {len(_prompt_history)})"
    )

    entry = _prompt_history[-1]
    assert "user_message" in entry, "Debug entry missing 'user_message' field"
    assert "full_prompt" in entry, "Debug entry missing 'full_prompt' field"
    assert "channel" in entry, "Debug entry missing 'channel' field"
    assert entry["user_message"] != "", "Debug entry 'user_message' is empty"
    assert entry["full_prompt"] != "", "Debug entry 'full_prompt' is empty"


# ---------------------------------------------------------------------------
# Test 3: MemoryWriteStage Always Runs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_write_stage_runs_on_halt():
    """MemoryWriteStage MUST run even when pipeline halts (e.g. bot ignores)."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_2_runners_pipeline import (
        MessagePipeline,
    )

    # Controller that tells bot to IGNORE (sets halt_reason)
    ctrl = MagicMock()
    ctrl.should_respond.return_value = (False, "boltzmann_ignore")

    pipeline = MessagePipeline.build(
        response_controller=ctrl,
        memory_system=_mock_memory_system(),
        retrieval=_mock_retrieval(),
        personality=_mock_personality(),
        temporal_context=MagicMock(),
        response_generator=_mock_response_generator(),
        thinking_filter=_mock_thinking_filter(),
        mention_translator=MagicMock(),
        mood_state=MagicMock(),
        client=MagicMock(),
        small_llm=MagicMock(),
        dynamics_engine=MagicMock(),
    )

    ctx = _mock_message_context()
    ctx = await pipeline.process(ctx)

    # MemoryWriteStage is the last stage (index 9)
    memory_stage = pipeline.stages[-1]
    assert memory_stage.__class__.__name__ == "MemoryWriteStage", (
        f"Last stage is {memory_stage.__class__.__name__}, expected MemoryWriteStage"
    )

    # The key assertion: even though the bot ignored, memory was still written.
    # Verify the stage's run() was actually invoked by checking timing
    assert "MemoryWriteStage" in ctx.stage_timings, (
        "MemoryWriteStage was skipped — not in stage_timings"
    )


# ---------------------------------------------------------------------------
# Test 4: Prompt Structure Is Valid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prompt_structure_valid():
    """Built messages must be a valid list of role/content dicts."""
    from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_1_act_runners.d4_3_prompt_assembly.d5_1_prompt_assembly import (
        PromptAssemblyStage,
    )

    ctx = _mock_message_context()
    stage = PromptAssemblyStage(
        mention_translator=MagicMock(),
        memory_system=_mock_memory_system(),
    )
    stage = await stage.run(ctx)

    # Every message must have role and content
    for i, msg in enumerate(ctx.built_messages):
        assert "role" in msg, f"Message {i} missing 'role'"
        assert "content" in msg, f"Message {i} missing 'content'"
        assert msg["role"] in ("system", "user", "assistant"), (
            f"Message {i} has invalid role: {msg['role']}"
        )
        assert isinstance(msg["content"], str), (
            f"Message {i} content is {type(msg['content'])}, expected str"
        )
