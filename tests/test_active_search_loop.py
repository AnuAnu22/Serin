import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ActiveSearchTest")

# --- MOCKS ---
# We mock EVERYTHING so we don't need real dependencies (numpy, qdrant, transformers, etc.)

class MockThinkingLLM:
    def __init__(self):
        self.step = 0

    async def send_input(self, prompt, **kwargs):
        self.step += 1
        if self.step == 1:
            logger.info(" LLM Step 1: Deciding to search for 'context'")
            return '{"search_needed": true, "query": "context", "reason": "need info"}'
        elif self.step == 2:
            logger.info(" LLM Step 2: Deciding to search for 'more context'")
            return '{"search_needed": true, "query": "more context", "reason": "need more info"}'
        else:
            logger.info(" LLM Step 3: Deciding to stop")
            return '{"search_needed": false, "reason": "enough info"}'

class MockMemory:
    def __init__(self):
        self.qdrant_client = MagicMock()
        
    def search_memories(self, query, **kwargs):
        logger.info(f" Memory System searching for: '{query}'")
        return [{'content': f"Memory about {query}", 'timestamp': '2023-01-01T12:00:00'}]

    # Mock all other methods used by EnhancedMessageManager
    def upsert_user(self, *args): pass
    def update_user_activity(self, *args): pass
    def log_activity(self, *args): pass
    def get_user_profile(self, *args): return {}
    def get_stats(self): return {}
    def store_recent_message(self, *args, **kwargs): pass
    def update_relationship(self, *args): pass
    def update_user_traits(self, *args): pass

# --- TEST ---
async def test_loop():
    print("🧪 Testing Active Search Loop (Max 2 Iterations)...")
    
    # We need to patch the imports inside EnhancedMessageManager so it doesn't try to load real libs
    import sys
    sys.modules['qdrant_memory_system'] = MagicMock()
    sys.modules['enhanced_memory_context'] = MagicMock()
    sys.modules['conversation_context_builder'] = MagicMock()
    sys.modules['response_controller'] = MagicMock()
    sys.modules['conversation_analyzer'] = MagicMock()
    sys.modules['bot_personality'] = MagicMock()
    sys.modules['vaderSentiment.vaderSentiment'] = MagicMock()
    sys.modules['natural_response_generator'] = MagicMock()
    sys.modules['long_message_handler'] = MagicMock()
    sys.modules['topic_fatigue'] = MagicMock()
    sys.modules['correction_handler'] = MagicMock()
    sys.modules['voice_tracker'] = MagicMock()
    sys.modules['visual_memory_system'] = MagicMock()
    sys.modules['models.model_factory'] = MagicMock()
    
    # Now we can import the class safely
    from serin.pipeline.ingest.core.manager import EnhancedMessageManagerV3
    from serin.pipeline.perceive.active_search import ActiveSearch

    # Setup Mocks
    mock_client = MagicMock()
    mock_translator = MagicMock()
    mock_translator.clean_for_bot.return_value = "Hello bot"
    mock_translator.clean_bot_self_mention.return_value = "Hello bot"
    
    mock_memory = MockMemory()
    
    # Initialize Manager
    # We mock the internal components that might trigger imports
    manager = EnhancedMessageManagerV3(
        client=mock_client,
        mention_translator=mock_translator,
        memory_system=mock_memory
    )
    
    # Manually inject our Mock LLM into the active_search component
    # (The constructor tries to load a real one, but we catch the exception or mock get_model_connector)
    manager.active_search = ActiveSearch(MockThinkingLLM())
    
    # Create a dummy message
    mock_msg = MagicMock()
    mock_msg.content = "Hello bot"
    mock_msg.author.id = 123
    mock_msg.author.display_name = "Tester"
    mock_msg.channel.id = 999
    mock_msg.created_at.isoformat.return_value = "2023-01-01T12:00:00"
    
    # Run process
    manager.current_batch = [mock_msg]
    await manager._flush_batch_with_enhanced_context(immediate=True)
    
    print("\n Test Complete. Check logs above for 'LLM Step 1' and 'LLM Step 2'.")

if __name__ == "__main__":
    asyncio.run(test_loop())
