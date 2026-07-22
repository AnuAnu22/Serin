"""Safe accessor for ``bot_state``.

Every route handler in this package used to do ``bot_state['some_key']``
directly. That works fine once ``init_bot_state()`` has run — but the panel's
uvicorn server and the Discord client's ``on_ready()`` startup sequence race
against each other (see ARCHITECTURE.md's startup flow: control panel starts
at step 14, well after most subsystems, but a request can arrive the instant
the port opens). Any request that lands before ``init_bot_state()`` completes,
or that asks for a key which is set on a different code path entirely (e.g.
``voice_behavior_manager``, set later in ``bot_pipeline_init``), raises a raw
``KeyError``. Handlers wrapped in a bare ``except Exception`` swallow it and
report a misleading "not initialized" message; handlers *without* a
try/except (several of the status routes) return a raw 500.

``get_component()`` replaces the indexing with an explicit, testable default,
so "not initialized yet" and "doesn't exist" both produce the same
predictable ``None`` instead of an exception whose type depends on which of
those two situations actually happened.
"""
from __future__ import annotations

from typing import Any

from serin.d1_5_ops_tooling.d2_1_control_panel.d3_2_panel_server.d4_3_server_state import (
    bot_state,
)


def get_component(key: str) -> Any | None:
    """Return ``bot_state[key]`` if present and initialized, else ``None``.

    Use this instead of ``bot_state[key]`` or ``bot_state.get(key)`` in every
    route handler — it's the same as ``.get()`` today, but gives callers one
    place to add readiness/health signalling later (e.g. distinguishing
    "key never registered" from "registered but still starting up") without
    touching every route file again.
    """
    return bot_state.get(key)
