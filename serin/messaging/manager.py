"""
Enhanced Message Manager - Professional Message Processing System
FIXES MEMORY CONTEXT ISSUE: Uses improved context building that works even when message crawler fails.
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import TYPE_CHECKING

import discord

from serin.memory.qdrant import QdrantMemorySystem
from serin.memory.context import EnhancedMemoryContext, ImprovedSystemPrompt
from conversation_context_builder import ConversationContextBuilder
from serin.messaging.response_controller import ResponseController, PersonalityState
from serin.personality.conversation_analyzer import ConversationAnalyzer
from serin.personality.bot_personality import BotPersonality
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from serin.core.logger import logger
from serin.messaging.response_generator import get_response_natural
from serin.messaging.long_message import analyze_message_length, get_length_handler
from serin.personality.topic_fatigue import get_fatigue_tracker
from serin.messaging.correction_handler import CorrectionDetector, MemoryCorrector, get_correction_acknowledgment
from voice.voice_tracker import VoiceTracker, get_voice_join_reaction, get_voice_duration_reaction
from serin.utils.debug_logger import log_message, log_context, log_correction, log_response
from serin.visual_memory_system import VisualMemorySystem
from serin.active_search import ActiveSearch
from voice.voice_action_decider import VoiceActionDecider
from models.factory import get_model_connector
import random
from serin.messaging.mention_translator import MentionTranslator
from typing import List, Dict, Optional, Tuple, Any, Set

class EnhancedMessageManagerV3:
    def __init__(
        self,
        client: discord.Client,
        mention_translator: MentionTranslator,
        memory_system: Optional[QdrantMemorySystem] = None,
        sub_timeout: int = 1,
        voice_output_manager: Any = None,  # Optional[VoiceOutputManager]
    ) -> None:
        self.client = client
        self.mention_translator = mention_translator
        self.current_batch: list[discord.Message] = []
        self.flush_task: Optional[asyncio.Task[None]] = None
        self.sub_timeout = sub_timeout
        self.voice_output_manager = voice_output_manager
        
        # TIER 8: Observable Brain State
        self.current_state: Dict[str, Any] = {
            'status': 'IDLE',  # IDLE, THINKING, GENERATING, SPEAKING
            'current_prompt': None,
            'current_user_message': None,
            'abort_flag': False,
            'last_activity': datetime.now().isoformat()
        }
        
        # Initialize memory system (Qdrant or ChromaDB)
        if memory_system:
            self.memory = memory_system
        else:
            # Default to Qdrant
            self.memory = QdrantMemorySystem()

        # Initialize LLM connector for image analysis
        self.llm = get_model_connector()

        # Initialize separate vision model (SmolVLM) if vision is enabled
        self.vision_llm: Any = None
        supports_vision = os.environ.get("LLM_SUPPORTS_VISION", "false").lower() in ("true", "1", "yes")
        vision_model = os.environ.get("VISION_MODEL", "smolvlm256m")
        if supports_vision:
            try:
                from models.vllm_connector import VLLMConnector
                self.vision_llm = VLLMConnector(model_name=vision_model)
                self.vision_llm.load_model()
                logger.info(f"👁️ Vision model loaded: {vision_model}")
            except Exception as e:
                logger.warning(f"⚠️ Vision model '{vision_model}' not available: {e}")
                self.vision_llm = None

        
        # Initialize context systems
        self.enhanced_context = EnhancedMemoryContext(self.memory)
        self.context_builder = ConversationContextBuilder(self.memory)
        self.analyzer = SentimentIntensityAnalyzer()
        
        # TIER 2: Human-like behavior
        self.response_controller = ResponseController()
        self.personality = PersonalityState()
        
        # TIER 3: Advanced features
        self.conversation_analyzer = ConversationAnalyzer()
        self.bot_personality = BotPersonality()
        
        # TIER 5: New systems
        self.correction_detector = CorrectionDetector()
        self.memory_corrector = MemoryCorrector(self.memory)
        self.voice_tracker = VoiceTracker(self.memory)
        
        # TIER 7: Active Search (Thinking Brain)
        # We need a model connector for this
        self.active_search: Optional[ActiveSearch] = None
        try:
            model_connector = get_model_connector()
            model_connector.load_model()
            self.active_search = ActiveSearch(model_connector)
            logger.info("   ✓ Active Search (Thinking) enabled")
        except Exception as e:
            self.active_search = None
            logger.error(f"❌ Active Search disabled: {e}")
        
        # TIER 6: Visual Cortex
        self.visual_memory: Optional[VisualMemorySystem] = None
        if hasattr(self.memory, 'qdrant_client') and self.memory.qdrant_client:
            self.visual_memory = VisualMemorySystem(self.memory.qdrant_client)
        else:
            self.visual_memory = None
            logger.warning("⚠️ Visual Cortex disabled (requires Qdrant)")
        
        # Track last bot response for correction detection
        self.last_bot_response: Optional[str] = None
        self.last_bot_response_channel: Optional[str] = None
        
        # Enhanced system prompt
        self.system_prompt = ImprovedSystemPrompt.get_enhanced_system_prompt()
        
        self.stats: Dict[str, int] = {
            'messages_processed': 0,
            'responses_generated': 0,
            'corrections_detected': 0,
            'errors': 0,
            'context_improvements': 0,
            'voice_responses': 0
        }

        # Cache for visual contexts between processing and flushing
        self.pending_visual_contexts: Dict[int, str] = {}

        # Voice pipeline (set externally if available)
        self.voice_pipeline: Any = None

        # TIER 7b: Voice Action Decider (structured output for join/leave decisions)
        self.voice_action_decider: Optional[VoiceActionDecider] = None
        self.voice_action_callback: Any = None  # Set by discord_bot.py
        try:
            va_connector = get_model_connector()
            va_connector.load_model()
            self.voice_action_decider = VoiceActionDecider(va_connector)
            logger.info("   ✓ Voice Action Decider enabled")
        except Exception as e:
            self.voice_action_decider = None
            logger.warning(f"⚠️ Voice Action Decider disabled: {e}")
        
        # Log memory system type
        memory_type = "Qdrant" if hasattr(self.memory, 'qdrant_client') else "ChromaDB"
        logger.info(f"✅ Enhanced MessageManager initialized with {memory_type} memory system")
        logger.info("   ✓ Improved memory context building")
        logger.info("   ✓ Works when message crawler fails")
        logger.info("   ✓ Better conversation continuity")
        if self.voice_output_manager:
            logger.info("   ✓ Voice Output Manager connected")

    def update_state(self, status: str, prompt: Optional[str] = None, user_message: Optional[str] = None) -> None:
        """Update the observable brain state"""
        self.current_state['status'] = status
        self.current_state['last_activity'] = datetime.now().isoformat()
        if prompt is not None:
            self.current_state['current_prompt'] = prompt
        if user_message is not None:
            self.current_state['current_user_message'] = user_message
            
    def abort_current_generation(self) -> None:
        """Signal to abort current generation"""
        logger.warning("🛑 Abort signal received!")
        self.current_state['abort_flag'] = True
        self.current_state['status'] = 'ABORTING'


    async def process_voice_input(self, user_id: str, username: str, channel_id: str, transcription: str, wav_b64: Optional[str] = None) -> None:
        """
        Process voice input and generate voice response.
        Uses sentence-level batching for low-latency voice response.
        """
        try:
            logger.info(f"🎤 Processing voice input from {username}: '{transcription}'")
            
            # 1. Build Context (Simpler than text context)
            # Get recent voice messages
            recent_voice = []
            if hasattr(self, 'voice_pipeline') and self.voice_pipeline:
                 recent_voice = self.voice_pipeline.get_recent_context(channel_id, limit=5)
            
            # Convert to format expected by context builder
            user_messages = []
            for msg in recent_voice:
                user_messages.append({
                    'user_id': msg['user_id'],
                    'user_name': msg['username'],
                    'content': msg['content'],
                    'timestamp': msg['timestamp']
                })
            
            # Add current message if not in history yet
            if not any(m['content'] == transcription for m in user_messages):
                user_messages.append({
                    'user_id': user_id,
                    'user_name': username,
                    'content': transcription if not wav_b64 else "[voice input]",
                    'timestamp': datetime.now().isoformat()
                })
            
            # Build context
            context = self.context_builder.build_context(
                user_messages=user_messages,
                channel_id=channel_id
            )
            
            formatted_context = self.context_builder.format_context_for_llm(context)
            
            # Add personality
            personality_context = self.bot_personality.get_personality_context()
            if personality_context:
                formatted_context += f"\n\n{personality_context}"
            
            # Add specific voice instruction
            formatted_context += "\n\n[SYSTEM: You are speaking in a voice channel. Keep responses concise, conversational, and natural. Avoid long lists or code blocks. Use fillers like 'Hmm' or 'Let's see' if you need to think.]"

            if wav_b64:
                # 2a. Direct audio + context in one shot (Gemma native multimodal)
                voice_messages = [{
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': formatted_context},
                        {'type': 'input_audio', 'input_audio': {'data': wav_b64, 'format': 'wav'}},
                    ],
                }]
                from serin.messaging.response_generator import llama as llm_connector
                if llm_connector is None:
                    from serin.messaging.response_generator import initialize_llama
                    await initialize_llama()
                    from serin.messaging.response_generator import llama as llm_connector
                response = await llm_connector.chat_completion(
                    voice_messages,
                    max_tokens=300,
                    temperature=1.0,
                    top_p=0.95,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
            else:
                # 2b. Text-only fallback (Whisper)
                response = await get_response_natural(
                    current_messages=user_messages,
                    context=formatted_context,
                    resolved_last_message=transcription,
                    tone_modifier=self.personality.get_tone_modifier(),
                    personality_state=self.personality.__dict__,
                    message_complexity="simple",
                    is_instruction=False
                )
            
            if response and response.strip():
                logger.info(f"🗣️ Voice Response: '{response}'")
                
                # 3. Send to Voice Output Manager
                if self.voice_output_manager:
                    try:
                        guild_id = int(context.get('guild_id', 0))
                        if guild_id == 0:
                            channel = self.client.get_channel(int(channel_id))
                            if channel:
                                guild_id = channel.guild.id
                        
                        if guild_id:
                            await self.voice_output_manager.speak(response, guild_id)
                            self.stats['voice_responses'] += 1
                        else:
                            logger.error("❌ Could not determine guild ID for voice response")
                    except Exception as e:
                        logger.error(f"❌ Error sending to voice output: {e}")
            
        except Exception as e:
            logger.exception(f"❌ Error processing voice input: {e}")

    async def start(self) -> None:
        logger.info("✅ Enhanced MessageManager started")
    
    async def process_message(self, message: discord.Message) -> None:
        """Process incoming message with enhanced context"""
        try:
            user_id = str(message.author.id)
            user_name = message.author.display_name
            content = message.content
            channel_id = str(message.channel.id)
            
            # Update mention cache
            self.mention_translator.update_cache(message.author)
            
            # Clean mentions for bot understanding
            cleaned_content = self.mention_translator.clean_for_bot(content, message)
            cleaned_content = self.mention_translator.clean_bot_self_mention(cleaned_content)
            log_message(message, cleaned_content)
            
            # TIER 5: Check for correction FIRST
            if self.last_bot_response and self.last_bot_response_channel == channel_id:
                correction = self.correction_detector.detect_correction(
                    message=cleaned_content,
                    previous_bot_response=self.last_bot_response,
                    context=[{'content': msg.content} for msg in self.current_batch[-3:]]
                )
                
                if correction and correction.get('confidence', 0) > 0.7:
                    logger.info("🔧 Correction detected!")
                    self.stats['corrections_detected'] += 1
                    log_correction(correction, user_name)
                    # Apply correction to memory
                    self.memory_corrector.apply_correction(
                        correction,
                        user_id,
                        user_name,
                        channel_id
                    )
                    
                    # Send natural acknowledgment
                    ack = get_correction_acknowledgment(correction)
                    await message.channel.send(ack)
                    
                    # Reset last response so we don't process it again
                    self.last_bot_response = None
                    return
            
            # TIER 6: Visual Memory Processing (MOVED UP)
            visual_context = ""
            main_llm_has_vision = os.environ.get("LLM_SUPPORTS_VISION", "false").lower() in ("true", "1", "yes")
            if message.attachments and self.visual_memory:
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith('image/'):
                        logger.info(f"👁️ Processing image from {user_name}...")
                        
                        # 1. Recall (Do I know this?) - use URL for CLIP
                        matches = self.visual_memory.recall_image(attachment.url)
                        
                        if matches:
                            top_match = matches[0]
                            visual_context += f"\n[Visual Memory: I recognize this image! It looks like what {top_match['username']} posted on {top_match['timestamp'][:10]}. Context: '{top_match['context']}']"
                            logger.info(f"💡 Visual recognition: {visual_context}")
                        
                        # Download image and encode as base64 ONCE for all pipelines
                        image_data_url = None
                        image_bytes = None
                        try:
                            image_bytes = await attachment.read()
                            if image_bytes:
                                mime = attachment.content_type or 'image/jpeg'
                                b64 = base64.b64encode(image_bytes).decode('utf-8')
                                image_data_url = f"data:{mime};base64,{b64}"
                                logger.info(f"📷 Encoded image as base64 ({len(image_bytes)} bytes)")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to download/encode image: {e}")
                        
                        # Store image data URL for VLM (or URL as fallback)
                        self.pending_visual_contexts[message.id] = image_data_url or attachment.url
                        
                        # Add visual indicator to content for LLM
                        cleaned_content += " [User posted an image]"
                        
                        # Generate description for memory storage
                        # Priority: gemma12b direct > SmolVLM fallback > no description
                        storage_description = ""
                        if image_data_url and main_llm_has_vision:
                            # Direct: use main LLM (gemma12b with mmproj)
                            try:
                                desc_prompt = [
                                    {"role": "user", "content": [
                                        {"type": "text", "text": "Describe this image in detail for archival purposes. Include any text you can read."},
                                        {"type": "image_url", "image_url": {"url": image_data_url}}
                                    ]}
                                ]
                                storage_description = await self.llm.chat_completion(desc_prompt, max_tokens=300)
                                logger.info(f"📝 Generated archival description (gemma12b): {storage_description[:100]}...")
                            except Exception as e:
                                logger.warning(f"⚠️ gemma12b vision failed for archival: {e}")
                                storage_description = "Image (vision model error)"
                        elif image_data_url and self.vision_llm:
                            # Fallback: use SmolVLM
                            try:
                                desc_prompt = [
                                    {"role": "user", "content": [
                                        {"type": "text", "text": "Describe this image in detail for archival purposes. Include any text you can read."},
                                        {"type": "image_url", "image_url": {"url": image_data_url}}
                                    ]}
                                ]
                                storage_description = await self.vision_llm.chat_completion(desc_prompt, max_tokens=300)
                                logger.info(f"📝 Generated archival description (SmolVLM): {storage_description[:100]}...")
                            except Exception as e:
                                logger.warning(f"⚠️ SmolVLM not available for archival: {e}")
                                storage_description = "Image (vision model error)"
                        elif image_data_url:
                            storage_description = "Image (vision model not loaded)"
                        else:
                            storage_description = "Image (could not download)"
                        
                        # 2. Store (Remember this) - use cached bytes for CLIP
                        storage_context = f"{cleaned_content}\n[Image Content: {storage_description}]"
                        if image_bytes:
                            self.visual_memory.store_image_from_bytes(
                                image_bytes=image_bytes,
                                image_url=attachment.url,
                                user_id=user_id,
                                username=user_name,
                                channel_id=channel_id,
                                context_text=storage_context
                            )
                        else:
                            self.visual_memory.store_image_memory(
                                image_url=attachment.url,
                                user_id=user_id,
                                username=user_name,
                                channel_id=channel_id,
                                context_text=storage_context
                            )
            
            # Update user profile
            self.memory.upsert_user(user_id, user_name, user_name)
            self.memory.update_user_activity(user_id, len(cleaned_content))
            
            # Calculate emotional tone BEFORE using it
            sentiment = self.analyzer.polarity_scores(cleaned_content)
            emotional_tone = self._get_emotional_tone(sentiment['compound'])
            
            # Get participants BEFORE using it
            participants = list(set([str(m.author.id) for m in self.current_batch] + [user_id]))
            
            # Store message as memory (using enhanced method if available)
            if hasattr(self.memory, 'add_memory_enhanced'):
                memory_id = self.memory.add_memory_enhanced(
                    content=cleaned_content,
                    user_id=user_id,
                    username=user_name,
                    channel_id=channel_id,
                    participants=participants,
                    emotional_tone=emotional_tone,
                    importance=0.5,
                    source_message_id=str(message.id)
                )
            else:
                raise ValueError("Memory system does not support enhanced memory addition")
            
            # Analyze and update personality
            self._analyze_personality(user_id, cleaned_content)

            # Store recent message in SQLite for context window
            try:
                self.memory.store_recent_message(
                    user_id=user_id,
                    username=user_name,
                    channel_id=channel_id,
                    content=cleaned_content,
                    message_id=str(message.id),
                    timestamp=message.created_at
                )
            except Exception as e:
                logger.debug(f"Could not store recent message: {e}")
            
            # Log activity
            self.memory.log_activity(user_id, channel_id, len(content), sentiment['compound'])
            
            # Add to batch
            self.current_batch.append(message)
            self.stats['messages_processed'] += 1
            
            # Check for bot mention
            bot_mentioned = self.client.user.mentioned_in(message)
            
            if bot_mentioned:
                logger.info("🎯 Bot mentioned - responding immediately")
                if self.flush_task and not self.flush_task.done():
                    self.flush_task.cancel()
                await self._flush_batch_with_enhanced_context(immediate=True)
            else:
                # Schedule delayed flush
                if self.flush_task and not self.flush_task.done():
                    self.flush_task.cancel()
                self.flush_task = asyncio.create_task(self._schedule_flush())
        
        except Exception as e:
            self.stats['errors'] += 1
            logger.exception(f"❌ Error processing message: {e}")
    
    async def _schedule_flush(self) -> None:
        """Schedule batch flush with timeout"""
        try:
            await asyncio.sleep(self.sub_timeout)
            await self._flush_batch_with_enhanced_context(immediate=False)
        except asyncio.CancelledError:
            pass
    
    async def _flush_batch_with_enhanced_context(self, immediate: bool) -> None:
        """Process batch with enhanced context building"""
        batch = self.current_batch
        self.current_batch = []
        self.flush_task = None

        if not batch:
            return

        channel = batch[0].channel

        try:
            from serin.messaging.stages import (
                ActiveSearchStage,
                ContextAssemblyStage,
                ConversationUpdateStage,
                GenerationStage,
                MemoryRetrievalStage,
                MessageContext,
                MessagePipeline,
                PipelineDeps,
                MessagePreparationStage,
                ResponseDecisionStage,
                VoiceActionStage,
            )

            deps = PipelineDeps(
                memory=self.memory,
                context_builder=self.context_builder,
                bot_personality=self.bot_personality,
                response_controller=self.response_controller,
                personality=self.personality,
                voice_tracker=self.voice_tracker,
                conversation_analyzer=self.conversation_analyzer,
                analyzer=self.analyzer,
                pending_visual_contexts=self.pending_visual_contexts,
                active_search=self.active_search,
                voice_action_decider=self.voice_action_decider,
                voice_action_callback=self.voice_action_callback,
                mention_translator=self.mention_translator,
                current_state=self.current_state,
                stats=self.stats,
                last_bot_response=self.last_bot_response,
                last_bot_response_channel=self.last_bot_response_channel,
            )

            pipeline = MessagePipeline(
                stages=[
                    MessagePreparationStage(),
                    MemoryRetrievalStage(),
                    ConversationUpdateStage(),
                    ResponseDecisionStage(),
                    ContextAssemblyStage(),
                    ActiveSearchStage(),
                    VoiceActionStage(),
                    GenerationStage(),
                ],
                deps=deps,
            )

            ctx = MessageContext(batch=batch, bot_mentioned=immediate)
            ctx = await pipeline.process(ctx)

            if ctx.response:
                self.last_bot_response = ctx.response
                self.last_bot_response_channel = str(ctx.channel.id)

            self.update_state(status='IDLE')

        except Exception as e:
            self.stats['errors'] += 1
            logger.exception(f"Error in enhanced batch flush: {e}")
            try:
                await channel.send("Sorry, had a brain fart. Try again?")
            except:
                pass
    
    def _analyze_personality(self, user_id: str, content: str) -> None:
        """Analyze message and update personality traits"""
        traits = []
        interests = []
        
        content_lower = content.lower()
        
        # Detect traits
        if any(w in content_lower for w in ['lol', 'haha', 'lmao', '😂']):
            traits.append('humorous')
        if any(w in content_lower for w in ['thanks', 'please', 'sorry']):
            traits.append('polite')
        if len(content) > 200:
            traits.append('verbose')
        elif len(content) < 20:
            traits.append('concise')
        if content.count('!') > 2:
            traits.append('enthusiastic')
        
        # Detect interests
        interest_keywords = {
            'gaming': ['game', 'play', 'steam', 'xbox', 'ps5'],
            'anime': ['anime', 'manga', 'weeb'],
            'music': ['song', 'music', 'band', 'album'],
            'tech': ['code', 'programming', 'ai', 'computer'],
            'art': ['draw', 'art', 'paint', 'sketch']
        }
        
        for interest, keywords in interest_keywords.items():
            if any(kw in content_lower for kw in keywords):
                interests.append(interest)
        
        if traits or interests:
            self.memory.update_user_traits(user_id, traits, interests)
    
    def _get_emotional_tone(self, sentiment_score: float) -> str:
        """Convert sentiment score to emotional tone"""
        if sentiment_score > 0.5:
            return 'happy'
        elif sentiment_score > 0.2:
            return 'positive'
        elif sentiment_score < -0.5:
            return 'sad'
        elif sentiment_score < -0.2:
            return 'negative'
        else:
            return 'neutral'
    
    def _detect_topic(self, content: str) -> Optional[str]:
        """Simple topic detection"""
        content_lower = content.lower()
        
        topics = {
            'gaming': ['game', 'gaming', 'play', 'steam', 'xbox', 'ps5', 'nintendo'],
            'anime': ['anime', 'manga', 'weeb'],
            'music': ['song', 'music', 'band', 'album', 'spotify'],
            'food': ['food', 'eat', 'cooking', 'recipe', 'restaurant'],
            'work': ['work', 'job', 'boss', 'office', 'meeting'],
            'school': ['school', 'class', 'homework', 'exam', 'teacher'],
            'movies': ['movie', 'film', 'cinema', 'netflix'],
            'sports': ['sport', 'football', 'basketball', 'soccer', 'gym']
        }
        
        for topic, keywords in topics.items():
            if any(kw in content_lower for kw in keywords):
                return topic
        
        return None
    
    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile"""
        return self.memory.get_user_profile(user_id)
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        stats = self.memory.get_stats()
        stats['manager_stats'] = self.stats
        stats['enhanced_context'] = {
            'improvements_used': self.stats['context_improvements'],
            'current_source': 'enhanced'  # All contexts now use enhanced system
        }
        
        # Add memory system type
        if hasattr(self.memory, 'qdrant_client'):
            stats['memory_system'] = 'Qdrant'
            stats['memory_features'] = {
                'hybrid_search': True,
                'bm25_available': hasattr(self.memory, 'bm25_index'),
                'embedding_available': hasattr(self.memory, 'embedding_model')
            }
        
        return stats


# Alias for backward compatibility with discord_bot.py
MessageManagerV3 = EnhancedMessageManagerV3
