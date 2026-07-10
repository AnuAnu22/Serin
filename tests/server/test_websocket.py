from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from serin.d1_5_ops_tooling.control_panel.server.state import active_websockets
from serin.d1_5_ops_tooling.control_panel.server.websocket import (
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

    async def test_sends_log_to_connected_ws(self) -> None:
        ws = _mock_ws(1)
        active_websockets.append(ws)

        await broadcast_log({"message": "hello world"})

        ws.send_json.assert_awaited_once_with(
            {"type": "log", "msg": "hello world"}
        )

    async def test_skips_disconnected_ws(self) -> None:
        ws = _mock_ws(0)  # disconnected
        active_websockets.append(ws)

        await broadcast_log({"message": "test"})

        ws.send_json.assert_not_awaited()

    async def test_removes_disconnected_ws(self) -> None:
        ws = _mock_ws(0)
        active_websockets.append(ws)

        await broadcast_log({"message": "x"})

        assert ws not in active_websockets

    async def test_removes_ws_that_raises(self) -> None:
        ws = _mock_ws(1)
        ws.send_json = AsyncMock(side_effect=RuntimeError("gone"))
        active_websockets.append(ws)

        await broadcast_log({"message": "x"})

        assert ws not in active_websockets

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

    async def test_handles_empty_active_list(self) -> None:
        await broadcast_log({"message": "x"})  # should not raise


class TestBroadcastEvent:
    """Unit tests for broadcast_event."""

    def setup_method(self) -> None:
        active_websockets.clear()

    async def test_sends_decision_event_directly(self) -> None:
        ws = _mock_ws(1)
        active_websockets.append(ws)
        data = {"action": "join", "user_id": "123"}

        await broadcast_event("decision", data)

        ws.send_json.assert_awaited_once_with(data)

    async def test_wraps_non_decision_event(self) -> None:
        ws = _mock_ws(1)
        active_websockets.append(ws)

        await broadcast_event("model_loaded", {"model": "gpt4"})

        ws.send_json.assert_awaited_once_with(
            {"type": "model_loaded", "data": {"model": "gpt4"}}
        )

    async def test_skips_disconnected_ws(self) -> None:
        ws = _mock_ws(0)
        active_websockets.append(ws)

        await broadcast_event("decision", {"x": 1})

        ws.send_json.assert_not_awaited()

    async def test_removes_ws_that_raises(self) -> None:
        ws = _mock_ws(1)
        ws.send_json = AsyncMock(side_effect=RuntimeError("gone"))
        active_websockets.append(ws)

        await broadcast_event("decision", {})

        assert ws not in active_websockets

    async def test_broadcasts_to_all_connected(self) -> None:
        ws1 = _mock_ws(1)
        ws2 = _mock_ws(1)
        active_websockets.extend([ws1, ws2])

        await broadcast_event("config_update", {"key": "x"})

        ws1.send_json.assert_awaited_once_with(
            {"type": "config_update", "data": {"key": "x"}}
        )
        ws2.send_json.assert_awaited_once_with(
            {"type": "config_update", "data": {"key": "x"}}
        )

    async def test_mixed_connected_and_disconnected(self) -> None:
        ws1 = _mock_ws(1)
        ws2 = _mock_ws(0)
        ws3 = _mock_ws(1)
        active_websockets.extend([ws1, ws2, ws3])

        await broadcast_event("decision", {"action": "leave"})

        ws1.send_json.assert_awaited_once_with({"action": "leave"})
        ws2.send_json.assert_not_awaited()
        ws3.send_json.assert_awaited_once_with({"action": "leave"})
        assert ws2 not in active_websockets
