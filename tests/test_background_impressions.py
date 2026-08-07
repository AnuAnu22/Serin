"""Tests for T11 — background LLM impressions (mocked LLM, valid/garbage JSON, cadence)."""
from unittest.mock import Mock

import pytest

from serin.d1_5_ops_tooling.d2_2_tooling_background.d5_1_tooling_background import (
    BackgroundProcessor,
)


class FakeStore:
    """Minimal fake store for testing."""
    def __init__(self):
        self.users_due = []
        self.messages = []
        self.affect_rows = {}

    def query_messages(self, user_id, limit, order_by):
        return [m for m in self.messages if m.get('user_id') == user_id][:limit]


class FakeAffectEngine:
    """Fake affect engine that records calls."""
    def __init__(self):
        self.apply_calls = []
        self.cached_snapshot = Mock(valence=0.0, familiarity=0.5, impression=None)

    def snapshot_cached(self, user_id):
        return self.cached_snapshot

    def build_impression_prompt(self, username, messages, valence):
        return f"prompt for {username}"

    @staticmethod
    def parse_impression(raw):
        # Delegate to the real implementation
        from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
            UserAffectEngine,
        )
        return UserAffectEngine.parse_impression(raw)

    async def apply_impression(self, user_id, text, delta):
        self.apply_calls.append((user_id, text, delta))


class FakeMemory:
    """Fake memory system with store and affect_engine."""
    def __init__(self, store, affect_engine):
        self.store = store
        self.affect_engine = affect_engine


@pytest.fixture
def fake_llm():
    """Fake LLM that returns valid JSON."""
    llm = Mock()
    llm.is_connected = True
    llm.generate = Mock(return_value='{"impression": "cool person", "valence_delta": 0.15}')
    return llm


@pytest.fixture
def processor_with_mocks(monkeypatch):
    """BackgroundProcessor with mocked dependencies."""
    store = FakeStore()
    affect = FakeAffectEngine()
    memory = FakeMemory(store, affect)

    processor = BackgroundProcessor(memory, max_queue_size=100)
    processor.is_running = True
    processor.extractor_llm = Mock()
    processor.extractor_llm.is_connected = True

    # Mock the store function
    def mock_get_users_due(store_arg, limit):
        return store.users_due[:limit]

    import serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_2_sqlite_store as sqlite_mod
    monkeypatch.setattr(sqlite_mod, "get_users_due_impression", mock_get_users_due)

    return processor, store, affect


@pytest.mark.asyncio
async def test_no_users_due_does_nothing(processor_with_mocks):
    """When no users are due, impression batch is a no-op."""
    processor, store, affect = processor_with_mocks
    store.users_due = []

    await processor._run_impression_batch()

    assert len(affect.apply_calls) == 0


@pytest.mark.asyncio
async def test_valid_json_applies_impression(processor_with_mocks, monkeypatch):
    """Valid LLM JSON applies the impression with clamped delta."""
    processor, store, affect = processor_with_mocks
    store.users_due = [{'user_id': 'u1'}]
    store.messages = [
        {'user_id': 'u1', 'username': 'Alice', 'content': 'hello'},
        {'user_id': 'u1', 'username': 'Alice', 'content': 'world'},
    ]

    # Mock asyncio.to_thread to just call the function
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    processor.extractor_llm.generate = Mock(
        return_value='{"impression": "very kind", "valence_delta": 0.15}'
    )

    await processor._run_impression_batch()

    assert len(affect.apply_calls) == 1
    user_id, text, delta = affect.apply_calls[0]
    assert user_id == 'u1'
    assert text == "very kind"
    assert delta == 0.15


@pytest.mark.asyncio
async def test_malformed_json_resets_counter(processor_with_mocks, monkeypatch):
    """Malformed JSON resets the counter (delta=0) to avoid retry loops."""
    processor, store, affect = processor_with_mocks
    store.users_due = [{'user_id': 'u2'}]
    store.messages = [{'user_id': 'u2', 'username': 'Bob', 'content': 'hi'}]

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    processor.extractor_llm.generate = Mock(return_value='not json at all')

    await processor._run_impression_batch()

    # Counter reset with empty text, delta 0
    assert len(affect.apply_calls) == 1
    user_id, text, delta = affect.apply_calls[0]
    assert user_id == 'u2'
    assert text == ""
    assert delta == 0.0


@pytest.mark.asyncio
async def test_no_messages_resets_counter(processor_with_mocks, monkeypatch):
    """User with no messages gets counter reset (shouldn't happen but graceful)."""
    processor, store, affect = processor_with_mocks
    store.users_due = [{'user_id': 'u3'}]
    store.messages = []

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    await processor._run_impression_batch()

    assert len(affect.apply_calls) == 1
    user_id, text, delta = affect.apply_calls[0]
    assert user_id == 'u3'
    assert text == ""
    assert delta == 0.0


@pytest.mark.asyncio
async def test_caps_at_3_users_per_cycle(processor_with_mocks, monkeypatch):
    """Impression batch processes max 3 users per run."""
    processor, store, affect = processor_with_mocks
    store.users_due = [
        {'user_id': 'u1'}, {'user_id': 'u2'}, {'user_id': 'u3'},
        {'user_id': 'u4'}, {'user_id': 'u5'}
    ]
    store.messages = [
        {'user_id': 'u1', 'username': 'A', 'content': 'hi'},
        {'user_id': 'u2', 'username': 'B', 'content': 'hi'},
        {'user_id': 'u3', 'username': 'C', 'content': 'hi'},
        {'user_id': 'u4', 'username': 'D', 'content': 'hi'},
        {'user_id': 'u5', 'username': 'E', 'content': 'hi'},
    ]

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    processor.extractor_llm.generate = Mock(
        return_value='{"impression": "nice", "valence_delta": 0.1}'
    )

    await processor._run_impression_batch()

    # Only 3 users processed (limit=3 in get_users_due_impression)
    assert len(affect.apply_calls) == 3
    processed_ids = {call[0] for call in affect.apply_calls}
    assert processed_ids == {'u1', 'u2', 'u3'}


@pytest.mark.asyncio
async def test_llm_disconnected_skips_batch(processor_with_mocks):
    """When LLM is not connected, impression batch is skipped."""
    processor, store, affect = processor_with_mocks
    store.users_due = [{'user_id': 'u1'}]
    store.messages = [{'user_id': 'u1', 'username': 'Alice', 'content': 'hi'}]

    processor.extractor_llm.is_connected = False

    await processor._run_impression_batch()

    assert len(affect.apply_calls) == 0


@pytest.mark.asyncio
async def test_exception_during_generation_resets_counter(processor_with_mocks, monkeypatch):
    """If LLM call throws, counter still gets reset to avoid infinite retry."""
    processor, store, affect = processor_with_mocks
    store.users_due = [{'user_id': 'u1'}]
    store.messages = [{'user_id': 'u1', 'username': 'Alice', 'content': 'hi'}]

    async def fake_to_thread(func, *args, **kwargs):
        raise RuntimeError("LLM exploded")
    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    await processor._run_impression_batch()

    # Counter reset on exception
    assert len(affect.apply_calls) == 1
    user_id, text, delta = affect.apply_calls[0]
    assert user_id == 'u1'
    assert text == ""
    assert delta == 0.0
