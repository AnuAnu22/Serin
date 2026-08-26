"""Contract: every HTTP path must be registered exactly once on the panel app.

Regression guard for the d5_2/d5_3 duplicate-route shadowing (CONNECTIONS-H):
two modules each registered /api/status, /api/stats and /api/health.
Starlette serves the FIRST-registered handler, so d5_3_server_status's
three routes were mounted-but-dead - anyone editing them saw no effect.
d5_3 was deleted in the dedup commit; these tests keep it that way.
"""
from __future__ import annotations

from collections import Counter

from fastapi.routing import APIRoute

from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server import app


def _http_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute)]


def test_no_duplicate_http_path_method_pairs() -> None:
    """No (path, method) pair may register twice - first wins, extras are dead.

    Distinct methods on one path (GET+POST) are normal REST design and fine;
    the d5_2/d5_3 bug was two GET handlers for the SAME path, where only the
    first registration ever serves traffic.
    """
    counts = Counter(
        (route.path, frozenset(route.methods or set())) for route in _http_routes()
    )
    dupes = {f"{path} {sorted(methods)}": n for (path, methods), n in counts.items() if n > 1}
    assert not dupes, (
        f"path+method registered more than once (only the first serves): {dupes}"
    )


def test_status_stats_health_served_by_server_state_module() -> None:
    """The canonical status/stats/health handlers must be the live ones."""
    expected = (
        "serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server"
        ".d4_7_state.d5_2_server_state"
    )
    watched = {"/api/status", "/api/stats", "/api/health"}
    seen: dict[str, str] = {}
    for route in _http_routes():
        if route.path in watched:
            seen[route.path] = route.endpoint.__module__
    assert set(seen) == watched, f"missing canonical routes: {watched - set(seen)}"
    for path, module in sorted(seen.items()):
        assert module == expected, (
            f"{path} is served by {module}; expected the d5_2_server_state copy"
        )
