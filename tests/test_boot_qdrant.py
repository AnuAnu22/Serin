"""Regression tests for the Qdrant boot readiness probe (discord_bot.py).

Qdrant >= 1.13 returns HTTP 404 on ``/health`` and HTTP 200 only on
``/healthz``. The pre-fix probe hit only ``/health``, so a perfectly healthy
container was reported as "not ready within 60s", stalling boot by a minute
and printing a misleading warning.

The fix probes ``/healthz`` first and falls back to ``/health`` for older
images. ``test_healthz_is_probed_first`` fails against the old logic.
"""

from collections.abc import Callable
from urllib.error import HTTPError

from discord_bot import _qdrant_running


def _urlopen_mock(
    healthz_ok: bool, health_ok: bool
) -> Callable[..., object]:
    """urlopen that serves a 200 (no exception) for a reachable endpoint.

    Unreachable endpoints raise HTTPError(404), which is what urlopen does
    for a non-2xx response and is exactly what the probe must tolerate.
    """

    def urlopen(url: str, timeout: int = 2) -> object:
        path = url.rsplit("/", 1)[-1]
        ok = {"healthz": healthz_ok, "health": health_ok}[path]
        if not ok:
            raise HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
        return object()

    return urlopen


def test_healthz_is_probed_first(monkeypatch):
    """Modern Qdrant (>=1.13): /healthz 200, /health 404 -> ready.

    This is the regression guard: the old probe only tried /health and
    reported a healthy container as not-ready.
    """
    monkeypatch.setattr(
        "urllib.request.urlopen", _urlopen_mock(healthz_ok=True, health_ok=False)
    )
    assert _qdrant_running(6333) is True


def test_falls_back_to_health_for_older_qdrant(monkeypatch):
    """Older Qdrant: /healthz 404, /health 200 -> still ready."""
    monkeypatch.setattr(
        "urllib.request.urlopen", _urlopen_mock(healthz_ok=False, health_ok=True)
    )
    assert _qdrant_running(6333) is True


def test_reports_down_when_all_probes_fail(monkeypatch):
    """Qdrant genuinely unreachable: both endpoints 404 -> not ready."""
    monkeypatch.setattr(
        "urllib.request.urlopen", _urlopen_mock(healthz_ok=False, health_ok=False)
    )
    assert _qdrant_running(6333) is False


def test_no_real_network(monkeypatch):
    """Sanity: the probe is fully mocked, never touches the network."""
    monkeypatch.setattr(
        "urllib.request.urlopen", _urlopen_mock(healthz_ok=True, health_ok=True)
    )
    assert _qdrant_running(6333) is True
