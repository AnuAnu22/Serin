"""Tests for the Scenario spec + MessageContext builder."""
from __future__ import annotations

from tools.pipeline_inspector.fake_message import FakeMessage
from tools.pipeline_inspector.scenario import Scenario


def test_scenario_builds_real_message_context():
    s = Scenario(content="hi, did you win?")
    ctx = s.build_context()
    assert ctx.raw_content == "hi, did you win?"
    assert ctx.user_id == "1234"
    assert ctx.channel_id == "inspector"
    assert not ctx.should_respond
    assert ctx.message.id is not None  # FakeMessage injected


def test_scenario_preserves_metadata_fields():
    s = Scenario(content="x", user_id="99", username="Rin", channel_id="c2",
                 is_mentioned=True)
    ctx = s.build_context()
    assert ctx.user_id == "99"
    assert ctx.username == "Rin"
    assert ctx.channel_id == "c2"
    assert ctx.is_mentioned is True


def test_fake_message_guild_none_is_safe():
    m = FakeMessage("c", author_id=5, channel_id=9)
    assert m.guild is None
    assert m.mentions == []
    assert m.author.id == 5
