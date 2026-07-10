from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient


class TestStatusRoutes:
    def test_get_status_online(self, client: TestClient) -> None:
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["online"] is True
        assert data["user"]["name"] == "SerinBot"
        assert data["guilds"] == []

    def test_get_status_offline(self, client: TestClient) -> None:
        from serin.d1_5_ops_tooling.control_panel.server.state import bot_state
        client_none = MagicMock()
        client_none.is_ready.return_value = False
        client_none.user = None
        client_none.guilds = None
        client_none.latency = 0
        bot_state["discord_client"] = client_none

        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["online"] is False

    def test_get_health(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "discord" in data["components"]
        assert data["components"]["discord"]["status"] == "ok"
        assert "memory" in data["components"]
        assert data["components"]["memory"]["status"] == "ok"

    def test_get_health_voice_disabled(self, client: TestClient) -> None:
        response = client.get("/api/health")
        data = response.json()
        assert data["components"]["voice_input"]["status"] == "disabled"
        assert data["components"]["tts"]["status"] == "disabled"

    def test_get_stats(self, client: TestClient) -> None:
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "manager" in data
        assert "background" in data
        assert "bot" in data
        assert data["bot"]["messages_processed"] == 100


class TestControlsRoutes:
    def test_get_allowed_channels(self, client: TestClient) -> None:
        response = client.get("/api/channels/allowed")
        assert response.status_code == 200
        data = response.json()
        assert "channels" in data
        assert isinstance(data["channels"], list)

    def test_start_background(self, client: TestClient) -> None:
        response = client.post("/api/background/start")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_stop_background(self, client: TestClient) -> None:
        response = client.post("/api/background/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_get_model_info(self, client: TestClient) -> None:
        response = client.get("/api/model")
        assert response.status_code == 200
        data = response.json()
        assert "error" in data or "model_name" in data
