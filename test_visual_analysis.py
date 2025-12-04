import logging
import sys
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("serin_ai")

# Mock Qdrant client
class MockQdrantClient:
    def get_collections(self):
        class Collections:
            collections = []
        return Collections()
    def create_collection(self, **kwargs):
        pass

try:
    from visual_memory_system import VisualMemorySystem
    
    print("Initializing VisualMemorySystem...")
    # Pass mock client since we only test analysis
    vms = VisualMemorySystem(MockQdrantClient())
    
    print("Testing analyze_image...")
    # Use a stable image URL (e.g. Python logo)
    url = "https://www.python.org/static/community_logos/python-logo-master-v3-TM.png"
    
    description = vms.analyze_image(url)
    print(f"Description: {description}")
    
    if description and "python" in description.lower():
        print("✅ SUCCESS: Image analyzed correctly")
    elif description:
        print(f"⚠️ PARTIAL SUCCESS: Description generated but might be off: {description}")
    else:
        print("❌ FAILURE: No description generated")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
