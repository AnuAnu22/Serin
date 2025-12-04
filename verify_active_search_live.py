import asyncio
import logging
import os
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LiveTest")

# Load env vars
load_dotenv()

async def test_live_active_search():
    print("🚀 Starting Live Active Search Test...")
    
    # 1. Initialize Real Components
    try:
        from config import config
        from models.vllm_connector import VLLMConnector
        from active_search import ActiveSearch
        from qdrant_memory_system import QdrantMemorySystem
        
        # Initialize Memory (Qdrant)
        print("💾 Connecting to Qdrant...")
        memory = QdrantMemorySystem(
            data_dir="./bot_data",
            qdrant_host=config.QDRANT_HOST,
            qdrant_port=config.QDRANT_PORT
        )
        
        # Force recreation of collection
        if memory.qdrant_client:
            print("♻️ Recreating collection 'memories'...")
            try:
                memory.qdrant_client.delete_collection("memories")
                print("   - Deleted existing collection")
            except:
                pass
            
            # Trigger setup
            memory._setup_collection()
            print("   - Collection setup triggered")
        
        # Initialize LLM (vLLM)
        print("🤖 Connecting to vLLM...")
        # VLLMConnector reads from env vars, so we set them if needed
        os.environ["VLLM_BASE_URL"] = "http://localhost:8000/v1"
        os.environ["LLM_MODEL"] = config.LLM_MODEL
        
        llm = VLLMConnector(model_name=config.LLM_MODEL)
        llm.load_model()
        
        # Initialize Active Search
        active_search = ActiveSearch(llm)
        
        # 2. Seed Memory (so we have something to find)
        print("🌱 Seeding memory with test data...")
        test_content = "The secret code for the project is BLUE-OMEGA-99."
        memory.add_memory(
            content=test_content,
            user_id="test_user",
            username="Tester",
            channel_id="123",
            participants=["test_user"],
            importance=0.9
        )
        
        # 3. Test Query
        query = "What is the secret code for the project?"
        context = "User: What is the secret code for the project?"
        
        print(f"\n❓ Testing Query: '{query}'")
        
        # 4. Run Analysis
        print("🤔 Asking LLM if search is needed...")
        needs_search, search_query, reason = await active_search.analyze_need_to_search(
            user_message=query,
            recent_context=context
        )
        
        print(f"\n🧠 Decision: {needs_search}")
        print(f"🔍 Query: {search_query}")
        print(f"💭 Reason: {reason}")
        
        if needs_search and search_query:
            print("\n📚 Executing Search...")
            results = memory.search_memories(search_query, n_results=3)
            print(f"✅ Found {len(results)} results:")
            for res in results:
                print(f"   - {res['content']} (Score: {res.get('relevance', 0):.2f})")
                
            # Verify we found the secret
            if any("BLUE-OMEGA-99" in r['content'] for r in results):
                print("\n🎉 SUCCESS: Retrieved the correct memory!")
            else:
                print("\n⚠️ WARNING: Search ran but didn't find the exact memory.")
        else:
            print("\n❌ FAILED: LLM decided not to search.")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_live_active_search())
