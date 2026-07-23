"""Message processing — voice input, message handling, batch flushing."""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from typing import Any

import discord

from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_3_correction_handler import (
    get_correction_acknowledgment,
)
from serin.d1_1_pipeline_flow.d2_5_flow_think.d3_3_response_generator import (
    get_response_natural,
)
from serin.d1_3_state_core.d2_5_core_logger import logger
from serin.d1_4_config_base.d2_1_base_config import config
from serin.d1_4_config_base.d2_2_debug_logger import log_correction, log_message


async def process_voice_input(self: Any, user_id: str, username: str, channel_id: str, transcription: str, guild_id: str | None = None) -> None:
    """Process voice transcription text and generate response.

    Called by VoiceMemoryPipeline for the Whisper STT path.
    For direct audio input (Gemma), _transcribe_and_store handles
    everything end-to-end and this function is bypassed.
    """
    try:
        logger.info("Processing voice input from %s: '%s'", username, transcription)

        recent_voice: list[dict[str, Any]] = []
        vp = getattr(self, 'voice_pipeline', None)
        if vp is None:
            logger.warning("voice_pipeline not available — no recent voice context")
        else:
            recent_voice = vp.get_recent_context(channel_id, limit=5)
            logger.debug("Got %d recent voice messages for channel %s", len(recent_voice), channel_id)

        user_messages = []
        for msg in recent_voice:
            user_messages.append({
                "user_id": msg["user_id"],
                "user_name": msg["username"],
                "content": msg["content"],
                "timestamp": msg["timestamp"],
            })

        if not any(m["content"] == transcription for m in user_messages):
            user_messages.append({
                "user_id": user_id,
                "user_name": username,
                "content": transcription,
                "timestamp": datetime.now().isoformat(),
            })
            logger.debug("Appended user message to voice context (%d total)", len(user_messages))

        context = self.context_builder.build_context(
            user_messages=user_messages,
            channel_id=channel_id,
        )
        logger.debug("Built context with %d messages", len(user_messages))
        formatted_context = self.context_builder.format_context_for_llm(context)

        personality_context = self.bot_personality.get_personality_context()
        if personality_context:
            formatted_context += f"\n\n{personality_context}"
        else:
            logger.debug("No personality context available")

        formatted_context += "\n\n[SYSTEM: You are speaking in a voice channel. Keep responses concise, conversational, and natural. Avoid long lists or code blocks. Use fillers like 'Hmm' or 'Let's see' if you need to think.]"

        response = await get_response_natural(
            current_messages=user_messages,
            context=formatted_context,
            resolved_last_message=transcription,
            tone_modifier=self.personality.get_tone_modifier(),
            personality_state=self.personality.__dict__,
            message_complexity="simple",
            is_instruction=False,
        )
        logger.debug("get_response_natural returned (%d chars)", len(response) if response else 0)

        if not response or not response.strip():
            logger.warning("Empty response from LLM — nothing to speak")
            return

        logger.info("Voice Response: '%s'", response[:200])
        if self.voice_output_manager is None:
            logger.warning("voice_output_manager not available — response not spoken")
            return

        if guild_id is None:
            logger.debug("No guild_id provided — resolving from channel %s", channel_id)
            channel = self.client.get_channel(int(channel_id))
            if channel:
                guild_id = str(channel.guild.id)
                logger.info("Resolved guild_id %s from channel %s", guild_id, channel_id)
            else:
                logger.error("Could not resolve guild — channel %s not cached", channel_id)
                return

        try:
            await self.voice_output_manager.speak(response, int(guild_id))
            self.stats["voice_responses"] += 1
            logger.info("TTS queued for guild %s (%d chars)", guild_id, len(response))
        except Exception as e:
            logger.exception("Failed to queue TTS for guild %s: %s", guild_id, e)

    except Exception as e:
        logger.exception("Error processing voice input: %s", e)

async def start(self: Any) -> None:
    """Start the manager."""
    logger.info("Enhanced MessageManager started")

async def process_message(self: Any, message: discord.Message) -> None:
    """Process incoming message with all pre-processing, then delegate to pipeline."""
    try:
        user_id = str(message.author.id)
        user_name = message.author.display_name
        content = message.content
        channel_id = str(message.channel.id)

        self.mention_translator.update_cache(message.author)
        cleaned_content = self.mention_translator.clean_for_bot(content, message)
        cleaned_content = self.mention_translator.clean_bot_self_mention(cleaned_content)
        log_message(message, cleaned_content)

        # TIER 5: Check for correction FIRST
        if self.last_bot_response and self.last_bot_response_channel == channel_id:
            correction = self.correction_detector.detect_correction(
                message=cleaned_content,
                previous_bot_response=self.last_bot_response,
                context=[{"content": msg.content} for msg in self.current_batch[-3:]],
            )
            if correction and correction.get("confidence", 0) > 0.7:
                logger.info("Correction detected!")
                self.stats["corrections_detected"] += 1
                log_correction(correction, user_name)
                self.memory_corrector.apply_correction(correction, user_id, user_name, channel_id)
                ack = get_correction_acknowledgment(correction)
                await message.channel.send(ack)
                self.last_bot_response = None
                return

        # TIER 6: Visual Memory Processing
        main_llm_has_vision = config.LLM_SUPPORTS_VISION
        if message.attachments and self.visual_memory:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    logger.info("Processing image from %s...", user_name)
                    matches = self.visual_memory.recall_image(attachment.url)
                    if matches:
                        top_match = matches[0]
                        visual_context = f"\n[Visual Memory: I recognize this image! It looks like what {top_match['username']} posted on {top_match['timestamp'][:10]}. Context: '{top_match['context']}']"
                        logger.info("Visual recognition: %s", visual_context)

                    image_data_url = None
                    image_bytes = None
                    try:
                        image_bytes = await attachment.read()
                        if image_bytes:
                            mime = attachment.content_type or "image/jpeg"
                            b64 = base64.b64encode(image_bytes).decode("utf-8")
                            image_data_url = f"data:{mime};base64,{b64}"
                            logger.info("Encoded image as base64 (%s bytes)", len(image_bytes))
                    except Exception as e:
                        logger.warning("Failed to download/encode image: %s", e)

                    self.pending_visual_contexts[message.id] = image_data_url or attachment.url
                    cleaned_content += " [User posted an image]"

                    storage_description = ""
                    if image_data_url and main_llm_has_vision:
                        try:
                            desc_prompt = [{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Describe this image in detail for archival purposes. Include any text you can read."},
                                    {"type": "image_url", "image_url": {"url": image_data_url}},
                                ],
                            }]
                            storage_description = await self.llm.chat_completion(desc_prompt, max_tokens=300)
                            logger.info("Generated archival description: %s...", storage_description[:100])
                        except Exception as e:
                            logger.warning("gemma12b vision failed for archival: %s", e)
                            storage_description = "Image (vision model error)"
                    elif image_data_url and self.vision_llm:
                        try:
                            desc_prompt = [{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Describe this image in detail for archival purposes. Include any text you can read."},
                                    {"type": "image_url", "image_url": {"url": image_data_url}},
                                ],
                            }]
                            storage_description = await self.vision_llm.chat_completion(desc_prompt, max_tokens=300)
                            logger.info("Generated archival description (SmolVLM): %s...", storage_description[:100])
                        except Exception as e:
                            logger.warning("SmolVLM not available for archival: %s", e)
                            storage_description = "Image (vision model error)"
                    elif image_data_url:
                        storage_description = "Image (vision model not loaded)"
                    else:
                        storage_description = "Image (could not download)"

                    storage_context = f"{cleaned_content}\n[Image Content: {storage_description}]"
                    if image_bytes:
                        self.visual_memory.store_image_from_bytes(
                            image_bytes=image_bytes,
                            image_url=attachment.url,
                            user_id=user_id,
                            username=user_name,
                            channel_id=channel_id,
                            context_text=storage_context,
                        )
                    else:
                        self.visual_memory.store_image_memory(
                            image_url=attachment.url,
                            user_id=user_id,
                            username=user_name,
                            channel_id=channel_id,
                            context_text=storage_context,
                        )

        # Update user profile
        self.memory.upsert_user(user_id, user_name, user_name)
        self.memory.update_user_activity(user_id, len(cleaned_content))

        sentiment = self.analyzer.polarity_scores(cleaned_content)
        emotional_tone = self._get_emotional_tone(sentiment["compound"])
        participants = list(set([str(m.author.id) for m in self.current_batch] + [user_id]))

        if hasattr(self.memory, "add_memory_enhanced"):
            # ── Perception: analyze before storage ────────────────────
            perception = self._perceive_message(
                cleaned_content, user_id, user_name
            )

            self.memory.add_memory_enhanced(
                content=cleaned_content,
                user_id=user_id,
                username=user_name,
                channel_id=channel_id,
                participants=participants,
                emotional_tone=emotional_tone,
                importance=0.8 if perception.is_objective else 0.3,
                memory_type='evidence' if perception.is_objective else 'utterance',
                source_message_id=str(message.id),
                speech_act=perception.speech_act,
                is_objective=perception.is_objective,
                evidence_class=perception.evidence_class,
                extracted_facts=[
                    f['content'] for f in perception.extracted_facts
                ],
            )

            # ── Store extracted facts in FactStore ────────────────────
            for fact in perception.extracted_facts:
                try:
                    self.memory.add_fact(
                        content=fact['content'],
                        category=fact['category'],
                        confidence=fact['confidence'],
                        source_message_id=str(message.id),
                        source_user_id=user_id,
                        source_username=user_name,
                        source_type=fact['source_type'],
                    )
                except Exception as e:
                    logger.debug("Could not store fact: %s", e)

            # ── Infer beliefs from updated facts ───────────────────────
            if perception.extracted_facts:
                try:
                    beliefs = self.memory.infer_beliefs_from_facts(
                        query=cleaned_content
                    )
                    for belief in beliefs:
                        self.memory.add_or_update_belief(
                            content=belief['content'],
                            category=belief['category'],
                            confidence=belief['confidence'],
                            supporting_fact_ids=belief.get('supporting_fact_ids'),
                            contradicting_fact_ids=belief.get('contradicting_fact_ids'),
                            evidence_count=belief.get('evidence_count', 1),
                            claim_count=belief.get('claim_count', 0),
                        )
                except Exception as e:
                    logger.debug("Could not infer beliefs: %s", e)
        else:
            raise ValueError("Memory system does not support enhanced memory addition")

        detected_traits = self._analyze_personality(user_id, cleaned_content)
        self.personality.update_from_conversation(
            conversation_mood=emotional_tone,
            user_traits=detected_traits,
            time_of_day=datetime.now().hour,
        )

        try:
            self.memory.store_recent_message(
                user_id=user_id,
                username=user_name,
                channel_id=channel_id,
                content=cleaned_content,
                message_id=str(message.id),
                timestamp=message.created_at,
            )
        except Exception as e:
            logger.debug("Could not store recent message: %s", e)

        try:
            self.memory.update_relationship(str(self.client.user.id), user_id)
        except Exception as e:
            logger.debug("Could not update relationship: %s", e)

        self.memory.log_activity(user_id, channel_id, len(content), sentiment["compound"])

        self.current_batch.append(message)
        self.stats["messages_processed"] += 1

        bot_mentioned = self.client.user.mentioned_in(message)
        if bot_mentioned:
            logger.info("Bot mentioned - responding immediately")
            if self.flush_task and not self.flush_task.done():
                self.flush_task.cancel()
            await self._flush_batch_with_enhanced_context(immediate=True)
        else:
            if self.flush_task and not self.flush_task.done():
                self.flush_task.cancel()
            self.flush_task = asyncio.create_task(self._schedule_flush())

    except Exception as e:
        self.stats["errors"] += 1
        logger.exception("Error processing message: %s", e)
