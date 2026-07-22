"""Tests for the control panel improvements: memory score breakdown, mood
history, and confirm-gating on destructive/sensitive routes.

Kept in a separate file from test_routes.py so a reviewer can see exactly
what's new without diffing the existing test file.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


class TestScoreBreakdown:
    """search_hybrid's _condense_results should surface the full scoring
    breakdown instead of collapsing everything to one 'relevance' float."""

    def test_condense_results_includes_score_breakdown(self) -> None:
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_1_search_store import (
            _condense_results,
        )

        store = MagicMock()
        candidates = [
            {
                'id': 'mem-1',
                'bm25_score': 2.5,
                'vector_score': 0.82,
                'combined_score': 0.65,
                'rerank_score': 0.71,
                'payload': {
                    'text': 'test memory',
                    'person_display': 'alice',
                    'timestamp': '',
                    'importance': 0.7,
                },
            }
        ]

        results = _condense_results(store, candidates)

        assert len(results) == 1
        breakdown = results[0]['score_breakdown']
        assert breakdown['bm25_score'] == 2.5
        assert breakdown['vector_score'] == 0.82
        assert breakdown['combined_score'] == 0.65
        assert breakdown['rerank_score'] == 0.71
        assert breakdown['importance_weight'] == 0.7
        assert 'formula' in breakdown
        # relevance still present for backwards compat with existing callers
        assert results[0]['relevance'] == 0.71

    def test_condense_results_handles_missing_scores_gracefully(self) -> None:
        """A candidate with no vector/bm25 score (e.g. one search backend
        down) shouldn't crash the condense step."""
        from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_1_remember_core.d4_1_core_storage.d5_1_search_store import (
            _condense_results,
        )

        store = MagicMock()
        candidates = [{'id': 'mem-2', 'payload': {'text': 'x'}}]

        results = _condense_results(store, candidates)
        assert results[0]['score_breakdown']['bm25_score'] == 0.0
        assert results[0]['score_breakdown']['vector_score'] == 0.0


class TestMoodHistory:
    def test_history_starts_with_initial_sample(self) -> None:
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_1_think_personality.d4_2_personality_state import (
            PersonalityState,
        )

        state = PersonalityState()
        history = state.get_history()
        assert len(history) == 1
        assert history[0]['energy_level'] == 0.5

    def test_update_appends_to_history(self) -> None:
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_1_think_personality.d4_2_personality_state import (
            PersonalityState,
        )

        state = PersonalityState()
        state.update_from_conversation('energetic', [], 10)
        state.update_from_conversation('chill', [], 20)

        history = state.get_history()
        assert len(history) == 3  # initial + 2 updates

    def test_history_is_bounded(self) -> None:
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_1_think_personality.d4_2_personality_state import (
            PersonalityState,
        )

        state = PersonalityState()
        for i in range(600):
            state.update_from_conversation('chill', [], i % 24)

        assert len(state.get_history(limit=10_000)) == 500  # capped at maxlen

    def test_set_mood_preset_applies_atomically(self) -> None:
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_1_think_personality.d4_2_personality_state import (
            PersonalityState,
        )

        state = PersonalityState()
        applied = state.set_mood_preset('high_energy')
        assert applied is True
        assert state.energy_level == 1.0
        assert state.engagement == 1.0

    def test_set_mood_preset_rejects_unknown_name(self) -> None:
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_1_think_personality.d4_2_personality_state import (
            PersonalityState,
        )

        state = PersonalityState()
        applied = state.set_mood_preset('definitely_not_a_real_preset')
        assert applied is False
        # state unchanged
        assert state.energy_level == 0.5


class TestMoodRoutes:
    def test_set_mood_valid_preset(self, client: TestClient) -> None:
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import bot_state
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_1_think_personality.d4_2_personality_state import (
            PersonalityState,
        )

        manager = MagicMock()
        manager.personality = PersonalityState()
        bot_state['message_manager'] = manager

        response = client.post('/api/mood/set', json={'mood': 'sass'})
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert manager.personality.sass_level == 1.0

    def test_set_mood_invalid_preset_returns_error_not_crash(self, client: TestClient) -> None:
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import bot_state
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_1_think_personality.d4_2_personality_state import (
            PersonalityState,
        )

        manager = MagicMock()
        manager.personality = PersonalityState()
        bot_state['message_manager'] = manager

        response = client.post('/api/mood/set', json={'mood': 'nonexistent'})
        assert response.status_code == 200
        assert response.json()['success'] is False

    def test_mood_history_endpoint(self, client: TestClient) -> None:
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import bot_state
        from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_1_think_personality.d4_2_personality_state import (
            PersonalityState,
        )

        manager = MagicMock()
        manager.personality = PersonalityState()
        bot_state['message_manager'] = manager

        response = client.get('/api/mood/history')
        assert response.status_code == 200
        assert 'history' in response.json()


class TestConfirmGatedRoutes:
    """Destructive/sensitive routes must not fire on a bare, unconfirmed POST."""

    def test_config_update_blocks_sensitive_key_without_confirm(
        self, client: TestClient
    ) -> None:
        response = client.post('/api/config', json={'LLM_BASE_URL': 'http://evil.example/v1'})
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False
        assert 'LLM_BASE_URL' in data['blocked_keys']

    def test_config_update_allows_sensitive_key_with_confirm(
        self, client: TestClient
    ) -> None:
        from serin.d1_4_config_base.d2_1_base_config import config

        original = config.LLM_BASE_URL
        try:
            response = client.post(
                '/api/config',
                json={'LLM_BASE_URL': 'http://localhost:9999/v1', 'confirm': True},
            )
            assert response.status_code == 200
            assert response.json()['success'] is True
            assert config.LLM_BASE_URL == 'http://localhost:9999/v1'
        finally:
            config.LLM_BASE_URL = original

    def test_config_update_allows_non_sensitive_keys_without_confirm(
        self, client: TestClient
    ) -> None:
        response = client.post('/api/config', json={'DEBUG_MODE': True})
        assert response.status_code == 200
        assert response.json()['success'] is True

    def test_restart_requires_confirm(self, client: TestClient) -> None:
        response = client.post('/api/bot/restart', json={})
        assert response.status_code == 200
        assert response.json()['success'] is False

    def test_restart_with_no_body_does_not_fire(self, client: TestClient) -> None:
        response = client.post('/api/bot/restart')
        assert response.status_code == 200
        assert response.json()['success'] is False


class TestLogsRecentUsesRealPath:
    def test_logs_recent_does_not_reference_stale_bot_log(self, client: TestClient) -> None:
        response = client.get('/api/logs/recent')
        assert response.status_code == 200
        data = response.json()
        # Whatever the outcome, it must not silently claim to read a file
        # ("bot.log") that nothing in the codebase writes to.
        if 'path' in data:
            assert 'bot.log' not in data['path']


class TestActiveWebsocketsLock:
    def test_lock_exists_and_is_asyncio_lock(self) -> None:
        import asyncio

        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
            active_websockets_lock,
        )

        assert isinstance(active_websockets_lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_concurrent_broadcast_and_disconnect_does_not_raise(self) -> None:
        """Regression test for the race between broadcast iterating
        active_websockets and a disconnect handler mutating it concurrently."""
        import asyncio

        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
            active_websockets,
            active_websockets_lock,
        )
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_5_server_websocket import (
            broadcast_log,
        )

        active_websockets.clear()
        fake_sockets = []
        for _ in range(20):
            ws = MagicMock()
            ws.client_state.value = 1
            ws.send_json = MagicMock(side_effect=lambda *a, **k: asyncio.sleep(0))
            fake_sockets.append(ws)
        active_websockets.extend(fake_sockets)

        async def disconnect_some() -> None:
            async with active_websockets_lock:
                for ws in fake_sockets[:10]:
                    if ws in active_websockets:
                        active_websockets.remove(ws)

        # Run a broadcast and a concurrent disconnect batch together; this
        # must not raise (e.g. "list changed size during iteration").
        await asyncio.gather(
            broadcast_log({'message': 'test'}),
            disconnect_some(),
        )
        active_websockets.clear()
