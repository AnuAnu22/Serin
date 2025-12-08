"""
Enhanced Message Manager - Professional Message Processing System
FIXES MEMORY CONTEXT ISSUE: Uses improved context building that works even when message crawler fails.
"""

import asyncio

from qdrant_memory_system import QdrantMemorySystem
from enhanced_memory_context import EnhancedMemoryContext, ImprovedSystemPrompt
from conversation_context_builder import ConversationContextBuilder
from response_controller import ResponseController, PersonalityState
from conversation_analyzer import ConversationAnalyzer
from bot_personality import BotPersonality
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from logger_config import logger
from natural_response_generator import get_response_natural
from long_message_handler import analyze_message_length, get_length_handler
from topic_fatigue import get_fatigue_tracker
from correction_handler import CorrectionDetector, MemoryCorrector, get_correction_acknowledgment
from voice_tracker import VoiceTracker, get_voice_join_reaction, get_voice_duration_reaction
from debug_logger import log_message, log_context, log_correction, log_response
from visual_memory_system import VisualMemorySystem
from active_search import ActiveSearch
from models.model_factory import get_model_connector
import random
from typing import List, Dict, Optional, Tuple

class EnhancedMessageManagerV3:
    def __init__(self, client, mention_translator, memory_system=None, sub_timeout=3, voice_output_manager=None):
        self.client = client
        self.mention_translator = mention_translator
        self.current_batch = []
        self.flush_task = None
        self.sub_timeout = sub_timeout
        self.voice_output_manager = voice_output_manager
        
        # TIER 8: Observable Brain State
        self.current_state = {
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
        try:
            model_connector = get_model_connector()
            model_connector.load_model()
            self.active_search = ActiveSearch(model_connector)
            logger.info("   ✓ Active Search (Thinking) enabled")
        except Exception as e:
            self.active_search = None
            logger.error(f"❌ Active Search disabled: {e}")
        
        # TIER 6: Visual Cortex
        if hasattr(self.memory, 'qdrant_client'):
            self.visual_memory = VisualMemorySystem(self.memory.qdrant_client)
        else:
            self.visual_memory = None
            logger.warning("⚠️ Visual Cortex disabled (requires Qdrant)")
        
        # Track last bot response for correction detection
        self.last_bot_response = None
        self.last_bot_response_channel = None
        
        # Enhanced system prompt
        self.system_prompt = ImprovedSystemPrompt.get_enhanced_system_prompt()
        
        self.stats = {
            'messages_processed': 0,
            'responses_generated': 0,
            'corrections_detected': 0,
            'errors': 0,
            'context_improvements': 0,
            'voice_responses': 0
        }
        
        # Cache for visual contexts between processing and flushing
        self.pending_visual_contexts = {}
        
        # Log memory system type
        memory_type = "Qdrant" if hasattr(self.memory, 'qdrant_client') else "ChromaDB"
        logger.info(f"✅ Enhanced MessageManager initialized with {memory_type} memory system")
        logger.info("   ✓ Improved memory context building")
        logger.info("   ✓ Works when message crawler fails")
        logger.info("   ✓ Better conversation continuity")
        if self.voice_output_manager:
            logger.info("   ✓ Voice Output Manager connected")

    def update_state(self, status: str, prompt: str = None, user_message: str = None):
        """Update the observable brain state"""
        self.current_state['status'] = status
        self.current_state['last_activity'] = datetime.now().isoformat()
        if prompt is not None:
            self.current_state['current_prompt'] = prompt
        if user_message is not None:
            self.current_state['current_user_message'] = user_message
            
    def abort_current_generation(self):
        """Signal to abort current generation"""
        logger.warning("🛑 Abort signal received!")
        self.current_state['abort_flag'] = True
        self.current_state['status'] = 'ABORTING'


    async def process_voice_input(self, user_id: str, username: str, channel_id: str, transcription: str):
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
                    'content': transcription,
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
            
            # 2. Generate Response
            # We use the same get_response_natural but we might want to stream it?
            # For now, let's generate full response and split it.
            # Ideally, we'd have a streaming LLM client here.
            
            response = await get_response_natural(
                current_messages=user_messages,
                context=formatted_context,
                resolved_last_message=transcription,
                tone_modifier=self.personality.get_tone_modifier(),
                personality_state=self.personality.__dict__,
                message_complexity=1, # Assume simple for voice
                is_instruction=False
            )
            
            if response and response.strip():
                logger.info(f"🗣️ Voice Response: '{response}'")
                
                # 3. Send to Voice Output Manager
                if self.voice_output_manager:
                    # Convert channel_id to int for voice client lookup
                    try:
                        guild_id = int(context.get('guild_id', 0)) # Context builder might not have guild_id
                        # Fallback: find guild from channel
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
            logger.error(f"❌ Error processing voice input: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def start(self):
        logger.info("✅ Enhanced MessageManager started")
    
    async def process_message(self, message):
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
            if message.attachments and self.visual_memory:
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith('image/'):
                        logger.info(f"👁️ Processing image from {user_name}...")
                        
                        # 1. Recall (Do I know this?)
                        matches = self.visual_memory.recall_image(attachment.url)
                        
                        if matches:
                            top_match = matches[0]
                            visual_context += f"\n[Visual Memory: I recognize this image! It looks like what {top_match['username']} posted on {top_match['timestamp'][:10]}. Context: '{top_match['context']}']"
                            logger.info(f"💡 Visual recognition: {visual_context}")
                        
                        # Store image URL for VLM (Qwen-VL)
                        # We no longer analyze locally with BLIP
                        self.pending_visual_contexts[message.id] = attachment.url
                        
                        # Add visual indicator to content for LLM
                        cleaned_content += " [User posted an image]"
                        
                        # Generate description for memory storage using VLM
                        # This ensures "past memory" has understanding
                        storage_description = ""
                        try:
                            # Initialize if needed
                            if not self.llm.client:
                                self.llm.load_model()
                                
                            # Ask VLM to describe
                            desc_prompt = [
                                {"role": "user", "content": [
                                    {"type": "text", "text": "Describe this image in detail for archival purposes. Include any text you can read."},
                                    {"type": "image_url", "image_url": {"url": attachment.url}}
                                ]}
                            ]
                            storage_description = await self.llm.chat_completion(desc_prompt, max_tokens=300)
                            logger.info(f"📝 Generated archival description: {storage_description[:100]}...")
                        except Exception as e:
                            logger.error(f"⚠️ Failed to generate archival description: {e}")
                            storage_description = "Image (description unavailable)"
                        
                        # 2. Store (Remember this)
                        # We use the message content AND VLM description as context
                        storage_context = f"{cleaned_content}\n[Image Content: {storage_description}]"
                            
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
            logger.error(f"❌ Error processing message: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _schedule_flush(self):
        """Schedule batch flush with timeout"""
        try:
            await asyncio.sleep(self.sub_timeout)
            await self._flush_batch_with_enhanced_context(immediate=False)
        except asyncio.CancelledError:
            pass
    
    async def _flush_batch_with_enhanced_context(self, immediate: bool):
        """Process batch with enhanced context building"""
        batch = self.current_batch
        self.current_batch = []
        self.flush_task = None
        
        # Filter out bot messages
        batch = [m for m in batch if not getattr(m.author, "bot", False)]
        
        if not batch:
            return
        
        try:
            channel = batch[0].channel
            
            # Prepare user messages
            user_messages = []
            for msg in batch:
                # Check for images in batch processing too
                content = self.mention_translator.clean_for_bot(msg.content, msg)
                if msg.attachments:
                    has_image = any(a.content_type and a.content_type.startswith('image/') for a in msg.attachments)
                    if has_image:
                        content += " [User posted an image]"

                message_payload = {
                    'user_id': str(msg.author.id),
                    'user_name': msg.author.display_name,
                    'content': content,
                    'timestamp': msg.created_at.isoformat()
                }
                
                # Check for pending image URL
                if msg.id in self.pending_visual_contexts:
                    # It's an image URL now, not a description
                    message_payload['image_url'] = self.pending_visual_contexts[msg.id]
                    del self.pending_visual_contexts[msg.id]

                user_messages.append(message_payload)
            
            # ENHANCED CONTEXT BUILDING - Using proper ConversationContextBuilder
            logger.debug("🧪 Building enhanced context...")
            
            # TIER 5: Check for Admin Instruction
            is_instruction = False
            last_msg_content = user_messages[-1]['content']
            last_msg_user = user_messages[-1]['user_name']
            
            if last_msg_content.startswith('/instruct'):
                # Security check: Only allow "Rin" (or creator)
                if 'rin' in last_msg_user.lower() or (self.response_controller.creator_id and user_messages[-1]['user_id'] == self.response_controller.creator_id):
                    logger.info(f"👮 Admin instruction detected from {last_msg_user}")
                    is_instruction = True
                    # Strip prefix
                    user_messages[-1]['content'] = last_msg_content.replace('/instruct', '', 1).strip()
                    # Force response
                    immediate = True
                else:
                    logger.warning(f"⚠️ Unauthorized /instruct attempt from {last_msg_user}")
            
            context = self.context_builder.build_context(
                user_messages=user_messages,
                channel_id=str(channel.id)
            )
            
            # CRITICAL FIX: Filter polluted memories (from previous bad summaries)
            garbage_patterns = [
                "We are given", "We must write", "CRITICAL RULES", "CRITICAL:",
                "one sentence", "Summary:", "Task:", "INSTRUCTIONS",
                "### FINAL", "[the ", "template", "example",
                "Output Format", "JSON", "search_needed", "query:",
                "username followed by", "third person"
            ]
            
            if 'relevant_memories' in context:
                clean_memories = []
                for mem in context['relevant_memories']:
                    content = mem.get('content', '')
                    is_garbage = any(pattern.lower() in content.lower() for pattern in garbage_patterns)
                    if is_garbage:
                        logger.warning(f"🧹 Filtered polluted memory: {content[:50]}...")
                        continue
                    clean_memories.append(mem)
                context['relevant_memories'] = clean_memories
            
            # Track context improvements
            self.stats['context_improvements'] += 1
            logger.info("📈 Using ConversationContextBuilder for context")
            
            log_context(context)
            
            # Rest of the logic remains the same...
            # TIER 5: Check voice context
            primary_user_id = user_messages[-1]['user_id']
            voice_info = self.voice_tracker.get_voice_info(primary_user_id)
            
            # Maybe mention voice status (30% chance if recently joined)
            if voice_info:
                duration = voice_info.get('duration_minutes', 0)
                if duration < 2:  # Just joined
                    voice_reaction = get_voice_join_reaction()
                    if voice_reaction:
                        await channel.send(voice_reaction)
                        await asyncio.sleep(random.uniform(1.0, 2.0))
            
            # Analyze message length
            length_analysis = analyze_message_length(user_messages[-1]['content'])
            
            # React to long messages
            length_handler = get_length_handler()
            personality_dict = self.personality.__dict__ if hasattr(self, 'personality') else None
            
            if length_handler.should_react_to_length(length_analysis, personality_dict):
                reaction = length_handler.get_length_reaction(length_analysis)
                if reaction:
                    await channel.send(reaction)
                    await asyncio.sleep(random.uniform(1.0, 2.0))
            
            # Topic fatigue tracking
            detected_topic = self._detect_topic(user_messages[-1]['content'])
            fatigue_tracker = get_fatigue_tracker()
            fatigue_level = 0.0
            
            if detected_topic:
                fatigue_tracker.track_topic(str(channel.id), detected_topic)
                fatigue_level = fatigue_tracker.get_topic_fatigue_level(str(channel.id), detected_topic)
                
                if fatigue_level > 0.3:
                    modified_state = fatigue_tracker.apply_fatigue_to_personality(
                        self.personality.__dict__,
                        fatigue_level
                    )
                    for key, value in modified_state.items():
                        setattr(self.personality, key, value)
            
            # Update relationships
            participants = list(set(um['user_id'] for um in user_messages))
            if len(participants) > 1:
                for i, user_a in enumerate(participants):
                    for user_b in participants[i+1:]:
                        self.memory.update_relationship(user_a, user_b, 'message')
            
            # Update conversation mood
            sentiment_scores = [
                self.analyzer.polarity_scores(msg['content'])['compound']
                for msg in user_messages
            ]
            self.response_controller.update_conversation_mood(
                str(channel.id),
                user_messages,
                sentiment_scores
            )
            
            # Update personality state
            primary_profile = context['profiles'].get(primary_user_id, {})
            primary_traits = primary_profile.get('personality_traits', [])
            conversation_mood = self.response_controller.conversation_mood.get(str(channel.id), 'neutral')
            
            self.personality.update_from_conversation(
                conversation_mood,
                primary_traits,
                datetime.now().hour
            )
            
            # SELECTIVE RESPONSE CHECK
            should_respond, reason = self.response_controller.should_respond(
                message_content=user_messages[-1]['content'],
                channel_id=str(channel.id),
                bot_mentioned=immediate,
                user_id=primary_user_id,
                recent_messages=context['recent_conversation']
            )
            log_response(should_respond, reason, user_messages[-1]['content'])
            
            if not should_respond and not is_instruction:
                logger.info(f"🤐 Skipping response (reason: {reason})")
                return
            
            logger.info(f"💬 Responding (reason: {reason})")
            
            # Conversation analysis
            conv_analysis = self.conversation_analyzer.analyze_conversation_flow(
                user_messages,
                str(channel.id)
            )
            
            logger.info(f"💬 Conversation: {conv_analysis['conversation_type']}")
            if conv_analysis['current_topic']:
                logger.info(f"📌 Topic: {conv_analysis['current_topic']}")
            
            # Check for preference triggers
            preference_trigger = self.bot_personality.detect_topic_in_message(user_messages[-1]['content'])
            
            preference_context = None
            if preference_trigger:
                category, item = preference_trigger
                preference_context = self.bot_personality.express_preference(category, item)
                logger.debug(f"💭 Preference: {preference_context}")
            
            # ENHANCED CONTEXT FORMATTING
            formatted_context = self.context_builder.format_context_for_llm(context)
            
            # Add personality context
            personality_context = self.bot_personality.get_personality_context()
            if personality_context:
                formatted_context += f"\n\n{personality_context}"
            
            if preference_context:
                formatted_context += f"\n\nNote: You think {preference_context}"
            
            # TIER 5: Add voice context if relevant
            if voice_info:
                channel_name = voice_info.get('channel_name', 'voice channel')
                duration = voice_info.get('duration_minutes', 0)
                formatted_context += f"\n\n[Note: {user_messages[-1]['user_name']} is currently in '{channel_name}' ({duration} min)]"
            
            # Resolve referents
            last_message = user_messages[-1]['content']
            # Note: This would need to be adapted for the enhanced context system
            resolved_message = last_message  # Simple fallback for now
            
            # Get tone modifier
            tone_modifier = self.personality.get_tone_modifier()
            
            logger.info("=" * 60)
            logger.info("🧠 ENHANCED CONTEXT PREPARED")
            logger.info("=" * 60)
            logger.info(f"Context source: {context.get('context_source', 'unknown')}")
            logger.info(f"Recent messages: {len(context['recent_conversation'])}")
            logger.info(f"Relevant memories: {len(context['relevant_memories'])}")
            logger.info(f"User profiles: {len(context['profiles'])}")
            logger.info(f"Relationships: {len(context['relationships'])}")
            logger.info(f"Conversation mood: {conversation_mood}")
            logger.info(f"Personality: {tone_modifier}")
            logger.info(f"Context improvements: {self.stats['context_improvements']}")
            logger.info("=" * 60)
            
            # 🔍 COMPREHENSIVE PROMPT DEBUG LOGGING
            logger.info("=" * 80)
            logger.info("🔍 COMPLETE PROMPT BEING SENT TO LLM")
            logger.info("=" * 80)
            logger.info("📨 CURRENT MESSAGES:")
            for i, msg in enumerate(user_messages):
                logger.info(f"  [{i}] {msg.get('user_name', 'Unknown')}: {msg.get('content', '')[:100]}...")
            
            logger.info(f"\n📋 FORMATTED CONTEXT LENGTH: {len(formatted_context)} characters")
            logger.info(f"📋 FORMATTED CONTEXT:\n{formatted_context}")
            
            logger.info(f"\n🎭 PERSONALITY STATE:")
            logger.info(f"  Tone modifier: {tone_modifier}")
            logger.info(f"  Message complexity: {length_analysis['complexity']}")
            
            logger.info(f"\n🔧 TECHNICAL PARAMETERS:")
            logger.info(f"  Resolved message: {resolved_message[:100]}...")
            logger.info(f"  Channel ID: {channel.id}")
            logger.info(f"  Channel name: {channel.name}")
            
            logger.info("=" * 80)
            logger.info("🚀 SENDING TO get_response_natural()")
            logger.info("=" * 80)
            
            # TIER 8: Update Observable State
            self.current_state['abort_flag'] = False # Reset flag
            self.update_state(
                status='THINKING',
                prompt=formatted_context,
                user_message=user_messages[-1]['content']
            )

            # TIER 7: Active Retrieval (Thinking Loop)
            active_search_results = []
            if self.active_search:
                logger.info("🤔 Entering Thinking Loop...")
                
                # Max loops: 2 (as requested for balance of depth vs speed)
                max_loops = 2
                loop_count = 0
                accumulated_results_str = ""
                
                while loop_count < max_loops:
                    # Decide if search is needed (or MORE search is needed)
                    needs_search, query, reason = await self.active_search.analyze_need_to_search(
                        user_message=user_messages[-1]['content'],
                        recent_context=formatted_context,
                        previous_results=accumulated_results_str if loop_count > 0 else None
                    )
                    
                    if needs_search and query:
                        logger.info(f"🧠 Thought (Iter {loop_count+1}): I need to search for '{query}' ({reason})")
                        
                        # Execute Search
                        new_results = self.memory.search_memories(
                            query=query,
                            user_id=primary_user_id,
                            n_results=3
                        )
                        logger.info(f"📚 Found {len(new_results)} results")
                        
                        if new_results:
                            # Add to accumulated results for the NEXT thinking step
                            accumulated_results_str += f"\nResults for '{query}':\n"
                            for mem in new_results:
                                accumulated_results_str += f"- {mem['content']} (from {mem['timestamp'][:10]})\n"
                            
                            # Add to final context immediately
                            formatted_context += f"\n\n--- ACTIVE RECALL (Iteration {loop_count+1}) ---\n"
                            formatted_context += f"Query: {query}\n"
                            for mem in new_results:
                                formatted_context += f"- {mem['content']} (from {mem['timestamp'][:10]})\n"
                            
                            active_search_results.extend(new_results)
                        else:
                            logger.info("   (No results found)")
                            accumulated_results_str += f"\nResults for '{query}': None found.\n"
                            # If we found nothing, the LLM might want to try a different query next time
                            
                        loop_count += 1
                    else:
                        logger.info(f"⚡ Thinking complete: No further search needed ({reason})")
                        break

            self.update_state(
                status='GENERATING',
                prompt=formatted_context,
                user_message=user_messages[-1]['content']
            )
            
            # Generate response with enhanced context
            response = await get_response_natural(
                current_messages=user_messages,
                context=formatted_context,
                resolved_last_message=resolved_message,
                tone_modifier=tone_modifier,
                personality_state=self.personality.__dict__,
                message_complexity=length_analysis['complexity'],
                is_instruction=is_instruction
            )
            
            # TIER 8: Check Abort Flag
            if self.current_state['abort_flag']:
                logger.warning("🛑 Response generation aborted by user!")
                self.update_state(status='IDLE', prompt=None)
                return

            if response and response.strip():
                # Truncate if too long
                if len(response) > 2000:
                    response = response[:1997] + "..."
                
                # Restore mentions
                response = self.mention_translator.restore_for_discord(response, channel.guild)
                
                # TIER 8: Update state to SPEAKING/SENDING
                self.update_state(status='SENDING')
                
                # Send with typing
                await self.response_controller.send_with_typing(
                    channel,
                    response,
                    simulate_typing=True,
                    message_complexity=length_analysis['complexity'],
                    has_question='?' in last_message
                )
                
                # Mark response
                self.response_controller.mark_response(str(channel.id))
                
                # TIER 5: Store last response for correction detection
                self.last_bot_response = response
                self.last_bot_response_channel = str(channel.id)
                
                self.stats['responses_generated'] += 1
                
                logger.info(f"✅ Enhanced response sent: '{response[:60]}...'")
            else:
                logger.warning("⚠️ Empty response generated, not sending")
            
            # Reset state
            self.update_state(status='IDLE')

        
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"❌ Error in enhanced batch flush: {e}")
            import traceback
            logger.error(traceback.format_exc())
            try:
                await channel.send("Sorry, had a brain fart. Try again?")
            except:
                pass
    
    def _analyze_personality(self, user_id: str, content: str):
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
    
    def get_user_profile(self, user_id: str) -> dict:
        """Get user profile"""
        return self.memory.get_user_profile(user_id)
    
    def get_memory_stats(self) -> dict:
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
