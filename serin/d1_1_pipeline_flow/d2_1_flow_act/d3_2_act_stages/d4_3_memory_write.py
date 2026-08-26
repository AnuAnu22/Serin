"""
MemoryWriteStage
----------------
Stores the conversation interaction (user message + bot response) in
Qdrant memory after the response has been sent. Also runs perception,
fact extraction, belief inference, relationship tracking, and personality
state updates — all of which were previously done in the old
``d4_5_message_process.py`` code path that the pipeline replaces.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Protocol

from serin.d1_1_pipeline_flow.d2_1_flow_act.d3_3_stages_base import PipelineStage
from serin.d1_3_state_core.d2_5_state_conversation.d3_2_message_context import (
    MessageContext,
)
from serin.d1_3_state_core.d2_5_state_conversation.d3_3_affect_engine import (
    relationship_category,
)
from serin.d1_4_config_base.d2_3_core_logger import logger


class DiscordClientLike(Protocol):
    """Structural type for the pieces of the Discord client we touch."""

    @property
    def user(self) -> DiscordUserLike | None: ...


class DiscordUserLike(Protocol):
    id: int


class MemoryWriteStage(PipelineStage):
    """Writes the interaction to the memory system after sending."""

    def __init__(self, memory_system: Any, personality: Any = None, client: DiscordClientLike | None = None, small_llm: Any = None, affect_engine: Any = None) -> None:
        self.memory = memory_system
        self.personality = personality
        self.client = client
        self.small_llm = small_llm
        self.affect_engine = affect_engine

    async def _run(self, ctx: MessageContext) -> MessageContext:
        content = ctx.raw_content
        user_id = ctx.user_id
        username = ctx.username
        channel_id = ctx.channel_id

        # ── Perception + fact extraction + personality update ────────────
        # These were previously in d4_5_message_process.py which is bypassed
        # by the pipeline. Run for EVERY message, even if the bot doesn't
        # respond.
        if content:
            try:
                # 1. Sentiment analysis
                compound = 0.0
                _analyzer: Any = None
                try:
                    from nltk.sentiment import SentimentIntensityAnalyzer
                    _analyzer = SentimentIntensityAnalyzer()
                    sentiment = _analyzer.polarity_scores(content)
                    compound = sentiment.get("compound", 0.0)
                except Exception as e:
                    logger.debug("nltk sentiment analysis unavailable: %s", e)

                emotional_tone = "neutral"
                if compound >= 0.5:
                    emotional_tone = "positive"
                elif compound <= -0.5:
                    emotional_tone = "negative"
                elif compound >= 0.05:
                    emotional_tone = "slight_positive"
                elif compound <= -0.05:
                    emotional_tone = "slight_negative"

                # 1b. Per-user affect update — feed sentiment into valence model
                if self.affect_engine is not None:
                    try:
                        await self.affect_engine.record_sentiment(user_id, float(compound))
                    except Exception as e:
                        logger.debug("affect record_sentiment failed: %s", e)

                # 2. Perception — classify message, extract facts
                from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_1_core_perception import (
                    perceive_message,
                )

                class _PerceptionSelf:
                    analyzer: Any = None
                _PerceptionSelf.analyzer = _analyzer

                perception = perceive_message(_PerceptionSelf(), content, user_id, username)
                logger.info("PERCEIVE CALLED: content=%s user=%s facts=%d", content[:60], username, len(perception.extracted_facts))

                # 3. Store user message in Qdrant with perception metadata
                try:
                    participants = [user_id]
                    if hasattr(ctx, "message") and ctx.message and hasattr(ctx.message, "author"):
                        participants = [str(m.id) for m in getattr(ctx.message, "mentions", [])] + [user_id]
                        participants = list(set(participants))

                    self.memory.add_memory_enhanced(
                        content=content,
                        user_id=user_id,
                        username=username,
                        channel_id=channel_id,
                        participants=participants,
                        emotional_tone=emotional_tone,
                        importance=0.8 if perception.is_objective else 0.3,
                        memory_type="evidence" if perception.is_objective else "utterance",
                        source_message_id=str(ctx.message.id) if ctx.message else "",
                        speech_act=perception.speech_act,
                        is_objective=perception.is_objective,
                        evidence_class=perception.evidence_class,
                        extracted_facts=[f["content"] for f in perception.extracted_facts],
                    )
                except Exception as e:
                    logger.exception("pipeline.memory_write_user_message_failed: %s", e)

                # 4. LLM-based fact extraction via Bayesian engine
                if self.small_llm is not None:
                    if not self.small_llm.is_connected:
                        try:
                            self.small_llm.load_model()
                        except Exception:
                            logger.exception("pipeline.llm_load_model_failed")
                    if self.small_llm.is_connected:
                        from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_1_core_perception.d5_2_perception_classify import (
                            detect_contradictions,
                            extract_facts_from_message,
                        )
                        try:
                            llm_facts = await extract_facts_from_message(
                                content, username, user_id, self.small_llm,
                            )
                            logger.info("LLM EXTRACTION: got %d facts", len(llm_facts))
                            for f in llm_facts:
                                sn = f.get("subject_username", "")
                                sid = str(ctx.user_id) if sn.lower() == username.lower() else "unknown"
                                self.memory.belief_engine.store_fact(
                                    subject_id=sid, subject_name=sn,
                                    claim=f.get("claim", ""),
                                    category=f.get("category", "observation"),
                                    source=username,
                                    source_type=f.get("source_type", "other"),
                                    initial_confidence=float(f.get("confidence", 0.4)),
                                )
                                logger.info("FACT BAYESIAN: subject=%s claim=%s", sn, f.get("claim", "")[:60])
                        except Exception as e:
                            logger.exception("pipeline.llm_fact_extraction_failed: %s", e)
                        try:
                            contradicted = await detect_contradictions(
                                content, username, user_id, self.memory, self.small_llm,
                            )
                            for fact_id in contradicted:
                                self.memory.belief_engine.observe(
                                    fact_id, user_id, "contradict", "self_contradict",
                                )
                                logger.info("FACT CONTRADICTED: fact_id=%s by %s", fact_id, username)
                        except Exception as e:
                            logger.exception("pipeline.contradiction_detection_failed: %s", e)
                    else:
                        logger.info("LLM EXTRACTION SKIPPED: LLM not connected")

                # 6. Update personality state
                if self.personality is not None:
                    try:
                        detected_traits: list[str] = []
                        if emotional_tone in ("positive", "slight_positive"):
                            detected_traits.append("positive")
                        if emotional_tone in ("negative", "slight_negative"):
                            detected_traits.append("negative")

                        # Derive the relationship bucket from this user's
                        # affect so the mood update is biased friend vs
                        # stranger vs enemy (emotional persistence).
                        relationship = None
                        if self.affect_engine is not None:
                            try:
                                snap = self.affect_engine.snapshot_cached(user_id)
                                relationship = relationship_category(
                                    snap.valence, snap.familiarity
                                )
                            except Exception as e:
                                logger.debug("relationship_category failed: %s", e)

                        self.personality.update_from_conversation(
                            conversation_mood=emotional_tone,
                            user_traits=detected_traits,
                            time_of_day=datetime.now().hour,
                            user_id=user_id,
                            relationship=relationship,
                        )
                    except Exception as e:
                        logger.exception("pipeline.personality_update_failed: %s", e)

                # 7. Update relationship
                if self.client is not None and self.client.user is not None:
                    try:
                        bot_user_id = str(self.client.user.id)
                        self.memory.update_relationship(bot_user_id, user_id)
                    except Exception as e:
                        logger.exception("pipeline.relationship_update_failed: %s", e)

                # 8. Log activity
                try:
                    self.memory.log_activity(user_id, channel_id, len(content), compound)
                except Exception as e:
                    logger.exception("pipeline.activity_log_failed: %s", e)

                logger.info("PERCEPTION COMPLETE: user=%s", username)

            except Exception as e:
                logger.exception("pipeline.perception_failed: %s", e)
        else:
            logger.debug("pipeline.perception_skipped_no_content", extra={
                "user": username,
            })

        # ── Store bot response if there is one ──────────────────────────
        if ctx.final_response:
            try:
                self.memory.add_memory_enhanced(
                    content=ctx.final_response,
                    user_id="serin",
                    username="Serin",
                    channel_id=ctx.channel_id,
                    participants=[ctx.user_id],
                    emotional_tone="neutral",
                    importance=0.1,
                    memory_type="bot_response",
                )

                # Cause 1 fix: the user's incoming message is persisted to the
                # SQLite recent_messages table by the ingest path, but the bot's
                # own reply was only ever written to Qdrant (memory_type=
                # "bot_response"). That made the table one-sided and hid the
                # bot's turns from the next turn's context. Mirror the user's
                # write here so recent_messages carries both sides of the
                # conversation. No-op when the pipeline halted without a reply
                # (halt_reason set, final_response empty) — guarded above by the
                # `if ctx.final_response` check.
                bot_user_id = "serin"
                if self.client is not None and self.client.user is not None:
                    bot_user_id = str(self.client.user.id)
                else:
                    logger.debug("pipeline.memory_write_bot_id_fallback")
                try:
                    self.memory.store_recent_message(
                        user_id=bot_user_id,
                        username="Serin",
                        channel_id=ctx.channel_id,
                        content=ctx.final_response,
                        message_id=f"bot_{int(time.time() * 1000)}",
                        timestamp=datetime.now(),
                    )
                except Exception as e:
                    logger.warning("pipeline.bot_recent_message_write_failed", extra={
                        "user": username,
                        "error": str(e),
                    })

                logger.debug("pipeline.memory_written", extra={
                    "user": username,
                    "response_len": len(ctx.final_response),
                })
            except Exception as e:
                logger.warning("pipeline.memory_write_failed", extra={
                    "user": username,
                    "error": str(e),
                })

        return ctx
