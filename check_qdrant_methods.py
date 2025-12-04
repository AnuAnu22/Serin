from qdrant_client import QdrantClient
import inspect

print("QdrantClient methods:")
client = QdrantClient(":memory:")
methods = [m for m in dir(client) if not m.startswith('_')]
print(methods)

if 'search' in methods:
    print("\n✅ 'search' method found!")
else:
    print("\n❌ 'search' method NOT found!")
