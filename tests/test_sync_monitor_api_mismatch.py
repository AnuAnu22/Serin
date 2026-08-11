"""
Regression test for MemorySyncMonitor._check_api_mismatches.

BackgroundProcessor.queue_message takes an *optional* ``message_id`` (default None),
which the backfill ``**msg`` path genuinely relies on (dicts from
get_messages_around_timestamp carry message_id). An optional parameter can never
cause a caller mismatch, so it must NOT be flagged. Only a *required* message_id
(no default) would be a real contract break.

History: d3_4_sync_monitor._check_api_mismatches used to flag ANY ``message_id``,
logging a false-positive "🔴 API MISMATCH" every 30s. The check was corrected to
flag only a required message_id. These tests pin that behavior.
"""
import asyncio

from serin.d1_1_pipeline_flow.d2_4_flow_remember.d3_4_sync_monitor import (
    MemorySyncMonitor,
)


class FakeBGProcessor:
    """Mirror of BackgroundProcessor.queue_message — message_id OPTIONAL (default None)."""

    def queue_message(
        self,
        content: str,
        username: str,
        user_id: str,
        channel_id: str,
        message_id: str | None = None,
        server_id: str = "",
        timestamp: str = "",
    ) -> None:
        pass


class FakeBGRequiredMessageID:
    """A genuinely broken API — message_id is REQUIRED (no default)."""

    def queue_message(
        self,
        content: str,
        username: str,
        user_id: str,
        channel_id: str,
        message_id: str,  # required — no default
    ) -> None:
        pass


def _check(monitor: MemorySyncMonitor) -> list[str]:
    asyncio.run(monitor._check_api_mismatches())
    return monitor.api_mismatches


def test_optional_message_id_is_not_flagged():
    """Optional message_id (the real signature) must NOT produce an API mismatch."""
    monitor = MemorySyncMonitor(object(), FakeBGProcessor(), object())
    errors = _check(monitor)
    msg_id_errors = [e for e in errors if "message_id" in e]
    assert msg_id_errors == [], f"optional message_id wrongly flagged: {msg_id_errors}"


def test_required_message_id_is_flagged():
    """A REQUIRED message_id (no default) is a real contract break and must be flagged."""
    monitor = MemorySyncMonitor(object(), FakeBGRequiredMessageID(), object())
    errors = _check(monitor)
    assert any("REQUIRED 'message_id'" in e for e in errors), \
        f"required message_id not flagged: {errors}"
