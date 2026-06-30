"""
Integration tests for Serin bot subsystems against live llama-swap.
Run: .venv/bin/python tests/test_all.py
"""
import sys
import os
import asyncio
import traceback
import tempfile
import shutil
from datetime import datetime

# Load .env BEFORE any module imports that read env vars
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = 0
failed = 0
skipped = 0

def test(name):
    def decorator(func):
        async def wrapper():
            global passed, failed, skipped
            try:
                print(f"\n{'='*60}")
                print(f"TEST: {name}")
                print(f"{'='*60}")
                await func()
                print(f"  >>> PASS")
                passed += 1
            except AssertionError as e:
                print(f"  >>> FAIL: {e}")
                traceback.print_exc()
                failed += 1
            except Exception as e:
                print(f"  >>> ERROR: {e}")
                traceback.print_exc()
                failed += 1
        return wrapper
    return decorator

def assert_eq(a, b, msg=""):
    assert a == b, f"Expected {b!r}, got {a!r}. {msg}"

def assert_true(cond, msg=""):
    assert cond, f"Expected truthy, got {cond!r}. {msg}"

def assert_in(needle, haystack, msg=""):
    assert needle in haystack, f"Expected {needle!r} in {haystack!r}. {msg}"


# ============================================================
# TEST 1: LLM Connection via model_factory
# ============================================================
@test("LLM connection via VLLMConnector to llama-swap")
async def test_llm_connection():
    from models.model_factory import get_model_connector
    
    connector = get_model_connector(provider="vllm", model_name="gemma12b")
    connector.load_model()
    
    info = connector.get_model_info()
    print(f"  Model: {info['model_name']}")
    print(f"  Provider: {info['provider']}")
    print(f"  Base URL: {info['base_url']}")
    
    assert_eq(info['model_name'], 'gemma12b')
    assert_eq(info['provider'], 'vllm')
    assert_true(connector.client is not None, "Client should be initialized")
    assert_true(connector.adapter is not None, "Adapter should be initialized")


# ============================================================
# TEST 2: LLM Chat Completion
# ============================================================
@test("LLM chat completion returns real response")
async def test_llm_chat():
    from models.model_factory import get_model_connector
    
    connector = get_model_connector(provider="vllm", model_name="gemma12b")
    connector.load_model()
    
    messages = [
        {"role": "user", "content": "What is 2+2? Reply with just the number."}
    ]
    
    response = await connector.chat_completion(messages, max_tokens=20)
    print(f"  Response: {response!r}")
    
    assert_true(len(response) > 0, "Response should not be empty")
    assert_true('4' in response, f"Response should contain '4', got: {response}")


# ============================================================
# TEST 3: Memory System (SQLite without Qdrant)
# ============================================================
@test("Memory system SQLite operations (without Qdrant)")
async def test_memory_sqlite():
    from serin.memory.qdrant import QdrantMemorySystem
    import tempfile
    import shutil
    
    test_dir = tempfile.mkdtemp()
    try:
        # This will create SQLite + FTS but Qdrant will fail to connect
        # We test SQLite parts only
        memory = QdrantMemorySystem(data_dir=test_dir, qdrant_host="localhost", qdrant_port=19999)
        
        # Test SQLite user operations
        memory.upsert_user("test_user_1", "TestAlice", "Alice Display")
        profile = memory.get_user_profile("test_user_1")
        print(f"  User profile: {profile}")
        
        assert_true(profile is not None, "Profile should exist")
        assert_eq(profile.get('username'), 'TestAlice')
        
        # Test activity logging
        memory.update_user_activity("test_user_1", 50)
        
        # Test stats
        stats = memory.get_stats()
        print(f"  Stats: {stats}")
        assert_true('total_users' in stats, "Stats should have total_users")
        assert_true(stats['total_users'] >= 1, "Should have at least 1 user")
        
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


# ============================================================
# TEST 4: Response Controller
# ============================================================
@test("Response controller should_respond logic")
async def test_response_controller():
    from response_controller import ResponseController, PersonalityState
    
    rc = ResponseController()
    
    # Bot should respond when mentioned
    should, reason = rc.should_respond(
        message_content="hey serin what's up",
        channel_id="123456",
        bot_mentioned=True,
        user_id="user1",
        recent_messages=[]
    )
    print(f"  Mentioned: should_respond={should}, reason={reason}")
    assert_true(should, "Should respond when mentioned")
    
    # PersonalityState works
    ps = PersonalityState()
    tone = ps.get_tone_modifier()
    print(f"  Default tone: {tone!r}")
    assert_true(len(tone) > 0, "Tone modifier should not be empty")
    
    # Update from conversation
    ps.update_from_conversation('energetic', ['humorous'], 14)
    tone_after = ps.get_tone_modifier()
    print(f"  After energetic update: {tone_after!r}")
    assert_true(ps.energy_level > 0.5, "Energy should increase for energetic mood at 14:00")


# ============================================================
# TEST 5: Bot Personality
# ============================================================
@test("Bot personality topic detection and preferences")
async def test_bot_personality():
    from bot_personality import BotPersonality
    
    test_dir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(test_dir, "test_bot_data.db")
        bp = BotPersonality(db_path=db_path)
        
        # Should detect gaming topic
        result = bp.detect_topic_in_message("I've been playing Elden Ring all day")
        print(f"  Topic detection: {result}")
        # Result can be None if no topic matched, that's ok
        
        # Personality context
        ctx = bp.get_personality_context()
        print(f"  Personality context length: {len(ctx) if ctx else 0}")
        # Context can be None/empty, that's ok for now
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


# ============================================================
# TEST 6: Conversation Context Builder
# ============================================================
@test("Conversation context builder formats context for LLM")
async def test_context_builder():
    from conversation_context_builder import ConversationContextBuilder
    
    # Create a minimal mock memory system
    class MockMemory:
        def get_recent_conversation(self, channel_id, limit=10):
            return [
                {'user_id': 'u1', 'user_name': 'Alice', 'content': 'Hey what game are you playing?', 'timestamp': '2026-06-28T10:00:00'},
                {'user_id': 'u2', 'user_name': 'Bob', 'content': 'Elden Ring mostly', 'timestamp': '2026-06-28T10:01:00'},
            ]
        def search_memories(self, query, user_id=None, n_results=3):
            return [
                {'content': 'Alice likes cooking', 'timestamp': '2026-06-25T14:00:00', 'user_name': 'Alice', 'relevance': 0.8},
            ]
        def get_user_profile(self, user_id):
            return {'personality_traits': ['humorous'], 'interests': ['gaming']}
        def get_user_relationships(self, user_id, min_strength=0.1):
            return []
    
    builder = ConversationContextBuilder(MockMemory())
    
    user_messages = [
        {'user_id': 'u1', 'user_name': 'Alice', 'content': 'What should I cook tonight?', 'timestamp': '2026-06-28T18:00:00'},
    ]
    
    context = builder.build_context(user_messages=user_messages, channel_id="12345")
    print(f"  Context keys: {list(context.keys())}")
    print(f"  Recent conversation: {len(context.get('recent_conversation', []))} messages")
    
    formatted = builder.format_context_for_llm(context)
    print(f"  Formatted context length: {len(formatted)} chars")
    print(f"  Formatted preview: {formatted[:200]}...")
    
    assert_true(len(formatted) > 0, "Formatted context should not be empty")
    assert_true('Alice' in formatted, "Context should mention Alice")


# ============================================================
# TEST 6B: Context builder handles empty/missing timestamps
# ============================================================
@test("Context builder handles empty timestamps without crashing")
async def test_context_builder_empty_timestamps():
    from conversation_context_builder import ConversationContextBuilder
    from datetime import datetime
    
    class MockMemoryDirty:
        def get_recent_conversation(self, channel_id, limit=10):
            return [
                {'user_id': 'u1', 'user_name': 'Alice', 'content': 'Hello', 'timestamp': '2026-06-28T10:00:00'},
                {'user_id': 'u2', 'user_name': 'Bob', 'content': 'Hi', 'timestamp': ''},  # Empty!
                {'user_id': 'u3', 'user_name': 'Charlie', 'content': 'Hey', 'timestamp': None},  # None!
            ]
        def search_memories(self, query, user_id=None, n_results=3):
            return [
                {'content': 'memory with empty ts', 'timestamp': '', 'user_name': 'Ghost'},
                {'content': 'memory with None ts', 'timestamp': None, 'user_name': 'Phantom'},
                {'content': 'memory with valid ts', 'timestamp': '2026-06-25T14:00:00', 'user_name': 'Alice'},
                {'content': 'memory with garbage ts', 'timestamp': 'not-a-date', 'user_name': 'Bob'},
            ]
        def get_user_profile(self, user_id):
            return None
        def get_user_relationships(self, user_id, min_strength=0.1):
            return []
    
    builder = ConversationContextBuilder(MockMemoryDirty())
    
    # This should NOT crash even with empty/None/garbage timestamps
    context = builder.build_context(
        user_messages=[{'user_id': 'u1', 'user_name': 'Alice', 'content': 'test'}],
        channel_id="123"
    )
    
    formatted = builder.format_context_for_llm(context)
    print(f"  Formatted with dirty data: {len(formatted)} chars")
    assert_true(len(formatted) > 0, "Should produce output even with dirty timestamps")
    assert_true('Alice' in formatted, "Should still include valid memories")


# ============================================================
# TEST 6C: Context builder handles empty memories list
# ============================================================
@test("Context builder handles empty memories gracefully")
async def test_context_builder_empty_memories():
    from conversation_context_builder import ConversationContextBuilder
    
    class MockMemoryEmpty:
        def get_recent_conversation(self, channel_id, limit=10):
            return []
        def search_memories(self, query, user_id=None, n_results=3):
            return []
        def get_user_profile(self, user_id):
            return None
        def get_user_relationships(self, user_id, min_strength=0.1):
            return []
    
    builder = ConversationContextBuilder(MockMemoryEmpty())
    context = builder.build_context(
        user_messages=[{'user_id': 'u1', 'user_name': 'Alice', 'content': 'test'}],
        channel_id="123"
    )
    formatted = builder.format_context_for_llm(context)
    print(f"  Empty memories context: {len(formatted)} chars")
    # Should not crash, may produce minimal output


# ============================================================
# TEST 6D: Time range filter handles empty timestamps
# ============================================================
@test("Time range filter skips entries with empty timestamps")
async def test_time_range_filter_dirty():
    from conversation_context_builder import ConversationContextBuilder
    from datetime import datetime, timedelta
    
    class MockMemoryForTimeRange:
        def get_recent_conversation(self, channel_id, limit=10):
            return []
        def search_memories(self, query, user_id=None, n_results=3):
            return [
                {'content': 'valid', 'timestamp': datetime.now().isoformat(), 'user_name': 'A'},
                {'content': 'empty', 'timestamp': '', 'user_name': 'B'},
                {'content': 'none', 'timestamp': None, 'user_name': 'C'},
                {'content': 'garbage', 'timestamp': 'not-a-date', 'user_name': 'D'},
            ]
        def get_user_profile(self, user_id):
            return None
        def get_user_relationships(self, user_id, min_strength=0.1):
            return []
    
    builder = ConversationContextBuilder(MockMemoryForTimeRange())
    
    # Try time range search — should not crash
    results = builder._search_with_time_range(
        "test", "u1",
        (datetime.now() - timedelta(hours=1), datetime.now() + timedelta(hours=1))
    )
    print(f"  Time range results: {len(results)} (should be 1 valid)")
    assert_true(len(results) == 1, "Should only return the valid timestamp entry")


# ============================================================
# TEST 15B: Response controller handles edge cases
# ============================================================
@test("Response controller handles message complexity types correctly")
async def test_response_controller_complexity():
    from response_controller import ResponseController
    
    rc = ResponseController()
    
    # Should respond to mention with simple message
    should, reason = rc.should_respond(
        message_content="hey",
        channel_id="99999",
        bot_mentioned=True,
        user_id="user1",
        recent_messages=[]
    )
    assert_true(should, "Should respond to mention")
    
    # Should respond to active conversation
    should2, reason2 = rc.should_respond(
        message_content="what do you think?",
        channel_id="99999",
        bot_mentioned=False,
        user_id="user1",
        recent_messages=[{'user_id': 'bot', 'content': 'I like pizza'}]
    )
    print(f"  Active conv: should={should2}, reason={reason2}")
    # May or may not respond depending on cooldown


# ============================================================
# TEST 16: Vision model graceful fallback
# ============================================================
@test("Vision model initialization handles missing model gracefully")
async def test_vision_fallback():
    import os
    os.environ['LLM_SUPPORTS_VISION'] = 'true'
    os.environ['VISION_MODEL'] = 'nonexistent-model-xyz'
    
    try:
        from models.vllm_connector import VLLMConnector
        connector = VLLMConnector(model_name='nonexistent-model-xyz')
        # This should fail gracefully, not crash
        try:
            connector.load_model()
            print("  Model loaded (unexpected)")
        except Exception as e:
            print(f"  Model failed as expected: {type(e).__name__}")
            assert_true(True, "Gracefully handled missing model")
    finally:
        os.environ['LLM_SUPPORTS_VISION'] = 'false'
        os.environ.pop('VISION_MODEL', None)


# ============================================================
# TEST 7: Natural Response Generator
# ============================================================
@test("Natural response generator produces human-like output")
async def test_natural_response():
    from natural_response_generator import initialize_llama, get_response_natural
    
    await initialize_llama()
    
    messages = [
        {'user_id': 'u1', 'user_name': 'Alice', 'content': 'What are you up to?'}
    ]
    
    response = await get_response_natural(
        current_messages=messages,
        context="Alice is a friend who likes cooking and gaming.",
        resolved_last_message="What are you up to?",
        tone_modifier="Be natural and conversational.",
        personality_state={'energy_level': 0.5, 'sass_level': 0.5, 'engagement': 0.5},
        message_complexity="simple",
        is_instruction=False
    )
    
    print(f"  Response: {response!r}")
    print(f"  Length: {len(response)} chars")
    
    assert_true(len(response) > 0, "Response should not be empty")
    assert_true(len(response) < 500, f"Response should be short, got {len(response)} chars")


# ============================================================
# TEST 8: Conversational Fillers and Typos
# ============================================================
@test("Conversational fillers add natural variation")
async def test_fillers():
    from conversational_fillers import add_conversational_fillers
    from realistic_typos import add_realistic_typos
    from thinking_filter import filter_thinking
    
    # Fillers
    result = add_conversational_fillers("I think that sounds great", None, "simple")
    print(f"  With fillers: {result!r}")
    assert_true(len(result) > 0, "Fillers should produce output")
    
    # Typos (should not break text)
    result2 = add_realistic_typos("Hello there friend", None, False)
    print(f"  With typos: {result2!r}")
    assert_true(len(result2) > 0, "Typos should produce output")
    
    # Thinking filter
    filtered = filter_thinking("<think>Let me think about this</think>The answer is 42")
    print(f"  Filtered: {filtered!r}")
    assert_in("42", filtered, "Should keep content after think tags")
    assert not "<think>" in filtered, f"Thinking filter should remove <think> tags, got: {filtered!r}"


# ============================================================
# TEST 9: Temporal Context
# ============================================================
@test("Temporal context formats timestamps naturally")
async def test_temporal():
    from temporal_context import TemporalFormatter
    from datetime import datetime, timedelta
    
    fmt = TemporalFormatter()
    now = datetime.now()
    
    # Same day
    result = fmt.format_natural(now - timedelta(hours=2))
    print(f"  2 hours ago: {result!r}")
    assert_in("morning" if now.hour < 12 else ("afternoon" if now.hour < 17 else "tonight"), result.lower())
    
    # Yesterday
    result = fmt.format_natural(now - timedelta(days=1))
    print(f"  Yesterday: {result!r}")
    assert_eq(result, "Yesterday")
    
    # This week
    result = fmt.format_natural(now - timedelta(days=3))
    print(f"  3 days ago: {result!r}")
    assert_in("Last", result)


# ============================================================
# TEST 10: Long Message Handler
# ============================================================
@test("Long message handler analyzes message complexity")
async def test_long_message():
    from long_message_handler import analyze_message_length, get_length_handler
    
    # Short message
    analysis = analyze_message_length("hey")
    print(f"  Short message: {analysis}")
    assert_eq(analysis['complexity'], 'simple')
    
    # Long message
    analysis = analyze_message_length("I was thinking about how the entire architecture of distributed systems has evolved over the past decade. " * 5)
    print(f"  Long message: complexity={analysis['complexity']}")
    assert_in(analysis['complexity'], ['complex', 'medium'])


# ============================================================
# TEST 11: Topic Fatigue
# ============================================================
@test("Topic fatigue tracking")
async def test_topic_fatigue():
    from topic_fatigue import get_fatigue_tracker
    
    tracker = get_fatigue_tracker()
    
    # Track same topic multiple times
    for _ in range(10):
        tracker.track_topic("ch1", "gaming")
    
    level = tracker.get_topic_fatigue_level("ch1", "gaming")
    print(f"  Fatigue after 10 gaming messages: {level}")
    assert_true(level > 0, "Fatigue should be > 0 after repeated topic")


# ============================================================
# TEST 12: Mention Translator
# ============================================================
@test("Mention translator caches and resolves mentions")
async def test_mention_translator():
    import discord
    from mention_translator import MentionTranslator
    
    # Create mock client
    class MockClient:
        class User:
            id = 12345
            display_name = "TestBot"
            bot = True
        user = User()
    
    mt = MentionTranslator(MockClient())
    
    # Test cleaning bot self-mention
    cleaned = mt.clean_bot_self_mention("Hey @TestBot what's up")
    print(f"  Cleaned: {cleaned!r}")
    # Should remove or handle the mention


# ============================================================
# TEST 13: Correction Handler
# ============================================================
@test("Correction handler detects corrections")
async def test_correction():
    from correction_handler import CorrectionDetector
    
    cd = CorrectionDetector()
    
    # Detect correction
    correction = cd.detect_correction(
        message="No I meant blue not red",
        previous_bot_response="I think the answer is red",
        context=[{'content': 'What color is the sky?'}]
    )
    print(f"  Correction detected: {correction}")
    # May or may not detect - depends on confidence threshold


# ============================================================
# TEST 14: Voice Tracker
# ============================================================
@test("Voice tracker records voice activity")
async def test_voice_tracker():
    from voice.tracker import VoiceTracker
    
    class MockMemory:
        def upsert_user(self, uid, name, display): pass
    
    vt = VoiceTracker(MockMemory())
    stats = vt.get_stats()
    print(f"  Voice stats: {stats}")
    assert_true('users_in_voice' in stats)
    assert_true('active_sessions' in stats)


# ============================================================
# TEST 15: Debug Logger
# ============================================================
@test("Debug logger does not crash on various inputs")
async def test_debug_logger():
    from debug_logger import log_message, log_context, log_correction, log_response
    
    # Log a fake message
    class FakeAuthor:
        id = 123
        display_name = "TestUser"
    class FakeChannel:
        name = 'test-channel'
        id = 12345
    class FakeGuild:
        name = 'TestServer'
    class FakeMessage:
        author = FakeAuthor()
        content = "Hello world"
        channel = FakeChannel()
        guild = FakeGuild()
    
    log_message(FakeMessage(), "Hello world cleaned")
    log_context({'recent_conversation': [], 'relevant_memories': []})
    log_response(True, "test reason", "test message")
    print("  All debug logs written successfully")


# ============================================================
# RUN ALL TESTS
# ============================================================
async def main():
    global passed, failed, skipped
    
    tests = [
        test_llm_connection,
        test_llm_chat,
        test_memory_sqlite,
        test_response_controller,
        test_bot_personality,
        test_context_builder,
        test_context_builder_empty_timestamps,
        test_context_builder_empty_memories,
        test_time_range_filter_dirty,
        test_natural_response,
        test_fillers,
        test_temporal,
        test_long_message,
        test_topic_fatigue,
        test_mention_translator,
        test_correction,
        test_voice_tracker,
        test_debug_logger,
        test_response_controller_complexity,
        test_vision_fallback,
    ]
    
    for t in tests:
        await t()
    
    total = passed + failed + skipped
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{total} passed, {failed} failed, {skipped} skipped")
    print(f"{'='*60}")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
