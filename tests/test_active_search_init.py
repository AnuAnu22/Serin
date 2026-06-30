import sys
import os
import asyncio
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from serin.pipeline.ingest.manager import EnhancedMessageManagerV3
from serin.state.model_system.interface import ModelInterface

# Mock dependencies
class MockModelConnector(ModelInterface):
    def __init__(self, model_name=None):
        self.loaded = False
        
    def load_model(self, temperature=None, top_p=None):
        print("MockModelConnector.load_model called")
        self.loaded = True
        
    async def chat_completion(self, messages, **kwargs):
        return "Mock response"
        
    async def send_input(self, prompt, **kwargs):
        return '{"search_needed": false}'
        
    def get_model_info(self):
        return {"model_name": "mock"}

# Mock get_model_connector in the module where it is used
import serin.pipeline.ingest.manager as enhanced_message_manager
enhanced_message_manager.get_model_connector = lambda **kwargs: MockModelConnector()

def test_initialization():
    print("Testing EnhancedMessageManagerV3 initialization...")
    
    client = MagicMock()
    mention_translator = MagicMock()
    memory_system = MagicMock()
    # Mock qdrant_client attribute to trigger Visual Memory initialization path (optional)
    memory_system.qdrant_client = MagicMock()
    
    manager = EnhancedMessageManagerV3(
        client=client,
        mention_translator=mention_translator,
        memory_system=memory_system
    )
    
    if manager.active_search:
        print("Active Search initialized successfully")
        if manager.active_search.llm.loaded:
             print("Model connector loaded successfully")
        else:
             print("FAIL: Model connector NOT loaded")
             sys.exit(1)
    else:
        print("FAIL: Active Search failed to initialize")
        sys.exit(1)

if __name__ == "__main__":
    test_initialization()
