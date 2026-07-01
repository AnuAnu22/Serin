import asyncio
from unittest.mock import AsyncMock, MagicMock
from serin.d1_1_pipeline_flow.d2_2_perceive_stage.active_search import ActiveSearch
from logger_config import logger

# Mock Model Interface
class MockModelConnector:
    async def send_input(self, prompt, temperature=0.1, max_tokens=150, stop=None):
        # Simulate LLM response based on prompt content
        if "database" in prompt:
            return '{"search_needed": true, "query": "database migration", "reason": "User asking about past topic"}'
        elif "capital of Mars" in prompt:
             return '{"search_needed": true, "query": "capital of Mars", "reason": "Fact check needed"}'
        else:
            return '{"search_needed": false, "reason": "No search needed"}'

async def test_active_search():
    print("🧪 Testing Active Search...")
    
    mock_llm = MockModelConnector()
    active_search = ActiveSearch(mock_llm)
    
    # Test 1: Fast Path (Heuristic Skip)
    print("\nTest 1: Fast Path (Should Skip)")
    needs_search, query, reason = await active_search.analyze_need_to_search("lol", "")
    print(f"Result: Search={needs_search}, Reason={reason}")
    assert needs_search is False
    assert reason == "heuristic_skip"
    print(" Passed")

    # Test 2: Slow Path (LLM Decision - Search Needed)
    print("\nTest 2: Slow Path (Search Needed)")
    needs_search, query, reason = await active_search.analyze_need_to_search("What did we say about the database?", "")
    print(f"Result: Search={needs_search}, Query='{query}', Reason={reason}")
    assert needs_search is True
    assert query == "database migration"
    print(" Passed")

    # Test 3: Slow Path (LLM Decision - No Search)
    print("\nTest 3: Slow Path (No Search Needed)")
    # We need a message long enough to pass heuristic but not triggering the mock's "true" condition
    long_message = "I am just telling you a story about my day and it was really long and boring."
    needs_search, query, reason = await active_search.analyze_need_to_search(long_message, "")
    print(f"Result: Search={needs_search}, Reason={reason}")
    assert needs_search is False
    print(" Passed")

if __name__ == "__main__":
    asyncio.run(test_active_search())
