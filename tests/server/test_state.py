from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestAuthMiddleware:
    """Tests for the control-panel auth middleware (check_auth)."""

    def test_no_auth_key_allows_all(self, client: TestClient) -> None:
        from serin.d1_4_config_base.d2_1_base_config import config

        original = config.CONTROL_PANEL_KEY
        config.CONTROL_PANEL_KEY = ""
        try:
            response = client.get("/api/status")
            assert response.status_code == 200
        finally:
            config.CONTROL_PANEL_KEY = original

    def test_auth_key_rejects_missing_header(self, client: TestClient) -> None:
        from serin.d1_4_config_base.d2_1_base_config import config

        original = config.CONTROL_PANEL_KEY
        config.CONTROL_PANEL_KEY = "secret123"
        try:
            response = client.get("/api/status")
            assert response.status_code == 401
            assert response.json() == {"error": "unauthorized"}
        finally:
            config.CONTROL_PANEL_KEY = original

    def test_auth_key_rejects_wrong_key(self, client: TestClient) -> None:
        from serin.d1_4_config_base.d2_1_base_config import config

        original = config.CONTROL_PANEL_KEY
        config.CONTROL_PANEL_KEY = "secret123"
        try:
            response = client.get("/api/status", headers={"X-API-Key": "wrong"})
            assert response.status_code == 401
        finally:
            config.CONTROL_PANEL_KEY = original

    def test_auth_key_allows_correct_key(self, client: TestClient) -> None:
        from serin.d1_4_config_base.d2_1_base_config import config

        original = config.CONTROL_PANEL_KEY
        config.CONTROL_PANEL_KEY = "secret123"
        try:
            response = client.get("/api/status", headers={"X-API-Key": "secret123"})
            assert response.status_code == 200
        finally:
            config.CONTROL_PANEL_KEY = original


class TestGetGpuVramUsage:
    """Tests for get_gpu_vram_usage with mocked subprocess."""

    def _mock_proc(self, **attrs: object) -> MagicMock:
        """Build a mock subprocess.Process.

        ``create_subprocess_exec`` is a coroutine, so we patch it with an async
        side-effect that returns the mock process.
        """
        proc = MagicMock(spec=["communicate", "kill", "wait", "returncode", "stdout"])
        proc.communicate = AsyncMock()
        proc.wait = AsyncMock()
        for k, v in attrs.items():
            setattr(proc, k, v)
        return proc

    def _patch_exec(self, mock_proc: MagicMock):
        async def _exec(*args: object, **kwargs: object) -> MagicMock:
            return mock_proc
        return patch.object(asyncio, "create_subprocess_exec", _exec)

    async def test_returns_zero_on_timeout(self) -> None:
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
            get_gpu_vram_usage,
        )

        mock_proc = self._mock_proc()
        mock_proc.communicate.side_effect = TimeoutError

        with self._patch_exec(mock_proc):
            result = await get_gpu_vram_usage()

        assert result == 0.0
        mock_proc.kill.assert_called_once()

    async def test_parses_nvidia_smi_output(self) -> None:
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
            get_gpu_vram_usage,
        )

        mock_stdout = MagicMock()
        mock_stdout.decode.return_value = "2048\n1024\n"
        mock_proc = self._mock_proc(returncode=0, stdout=mock_stdout)
        mock_proc.communicate.return_value = (mock_stdout, b"")

        with self._patch_exec(mock_proc):
            result = await get_gpu_vram_usage()

        assert result == 3.0

    async def test_returns_zero_on_nonzero_returncode(self) -> None:
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
            get_gpu_vram_usage,
        )

        mock_proc = self._mock_proc(returncode=1)
        mock_proc.communicate.return_value = (b"", b"error")

        with self._patch_exec(mock_proc):
            result = await get_gpu_vram_usage()

        assert result == 0.0

    async def test_returns_zero_on_exception(self) -> None:
        from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
            get_gpu_vram_usage,
        )

        with patch.object(
            asyncio, "create_subprocess_exec", side_effect=FileNotFoundError
        ):
            result = await get_gpu_vram_usage()

        assert result == 0.0
