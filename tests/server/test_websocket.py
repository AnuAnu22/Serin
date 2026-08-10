from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_7_state.d5_1_state_access import (
    active_websockets,
)
from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_8_server.d5_2_server_websocket import (
    broadcast_event,
    broadcast_log,
)


def _mock_ws(state_value: int = 1) -> MagicMock:
    """Build a mock WebSocket with a given client_state.value."""
    ws = AsyncMock()
    ws.client_state = MagicMock()
    ws.client_state.value = state_value
    return ws


class TestBroadcastLog:
    """Unit tests for broadcast_log."""

    def setup_method(self) -> None:
        active_websockets.clear()

    @pytest.mark.asyncio
    async def test_sends_log_to_connected_ws(self) -> None:
        ws = _mock_ws(1)
        active_websockets.append(ws)

        await broadcast_log({"message": "hello world"})

        ws.send_json.assert_awaited_once()
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "log"
        assert sent["msg"] == "hello world"

    @pytest.mark.asyncio
    async def test_skips_disconnected_ws(self) -> None:
        ws = _mock_ws(0)  # disconnected
        active_websockets.append(ws)

        await broadcast_log({"message": "test"})

        ws.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_removes_disconnected_ws(self) -> None:
        ws = _mock_ws(0)
        active_websockets.append(ws)

        await broadcast_log({"message": "x"})

        assert ws not in active_websockets

    @pytest.mark.asyncio
    async def test_removes_ws_that_raises(self) -> None:
        ws = _mock_ws(1)
        ws.send_json = AsyncMock(side_effect=RuntimeError("gone"))
        active_websockets.append(ws)

        await broadcast_log({"message": "x"})

        assert ws not in active_websockets

    @pytest.mark.asyncio
    async def test_removes_multiple_disconnected_ws(self) -> None:
        ws1 = _mock_ws(0)
        ws2 = _mock_ws(0)
        ws3 = _mock_ws(1)  # stays connected
        active_websockets.extend([ws1, ws2, ws3])

        await broadcast_log({"message": "x"})

        assert ws1 not in active_websockets
        assert ws2 not in active_websockets
        assert ws3 in active_websockets
        ws3.send_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handles_empty_active_list(self) -> None:
        await broadcast_log({"message": "x"})  # should not raise


class TestBroadcastEvent:
    """Unit tests for broadcast_event."""

    def setup_method(self) -> None:
        active_websockets.clear()

    @pytest.mark.asyncio
    async def test_sends_decision_event_directly(self) -> None:
        ws = _mock_ws(1)
        active_websockets.append(ws)
        data = {"action": "join", "user_id": "123"}

        await broadcast_event("decision", data)

        ws.send_json.assert_awaited_once()
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "decision"
        assert sent["data"] == data

    @pytest.mark.asyncio
    async def test_wraps_non_decision_event(self) -> None:
        ws = _mock_ws(1)
        active_websockets.append(ws)

        await broadcast_event("model_loaded", {"model": "gpt4"})

        ws.send_json.assert_awaited_once()
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "model_loaded"
        assert sent["data"] == {"model": "gpt4"}

    @pytest.mark.asyncio
    async def test_skips_disconnected_ws(self) -> None:
        ws = _mock_ws(0)
        active_websockets.append(ws)

        await broadcast_event("decision", {"x": 1})

        ws.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_removes_ws_that_raises(self) -> None:
        ws = _mock_ws(1)
        ws.send_json = AsyncMock(side_effect=RuntimeError("gone"))
        active_websockets.append(ws)

        await broadcast_event("decision", {})

        assert ws not in active_websockets

    @pytest.mark.asyncio
    async def test_broadcasts_to_all_connected(self) -> None:
        ws1 = _mock_ws(1)
        ws2 = _mock_ws(1)
        active_websockets.extend([ws1, ws2])

        await broadcast_event("config_update", {"key": "x"})

        ws1.send_json.assert_awaited_once()
        ws2.send_json.assert_awaited_once()
        sent1 = ws1.send_json.call_args[0][0]
        sent2 = ws2.send_json.call_args[0][0]
        assert sent1["type"] == "config_update"
        assert sent1["data"] == {"key": "x"}
        assert sent2["type"] == "config_update"
        assert sent2["data"] == {"key": "x"}

    @pytest.mark.asyncio
    async def test_mixed_connected_and_disconnected(self) -> None:
        ws1 = _mock_ws(1)
        ws2 = _mock_ws(0)
        ws3 = _mock_ws(1)
        active_websockets.extend([ws1, ws2, ws3])
        expected = {"action": "leave"}

        await broadcast_event("decision", expected)

        ws1.send_json.assert_awaited_once()
        sent1 = ws1.send_json.call_args[0][0]
        assert sent1["type"] == "decision"
        assert sent1["data"] == expected
        ws2.send_json.assert_not_awaited()
        ws3.send_json.assert_awaited_once()
        sent3 = ws3.send_json.call_args[0][0]
        assert sent3["type"] == "decision"
        assert sent3["data"] == expected
        assert ws2 not in active_websockets
