# Qdrant Migration Troubleshooting Guide

## Common Issues and Solutions

### Qdrant Connection Issues

#### Problem: Qdrant Service Not Starting
**Symptoms:**
- Docker container fails to start
- Qdrant port 6333 not accessible
- Error: "connection refused"

**Solutions:**
```bash
# Check Docker status
docker ps -a

# Remove existing container if corrupted
docker stop qdrant-serin
docker rm qdrant-serin

# Pull fresh image
docker pull qdrant/qdrant:v1.12.0

# Start fresh container
docker run -d \
  --name qdrant-serin \
  -p 6333:6333 \
  -v ./bot_data/qdrant_data:/qdrant/storage \
  qdrant/qdrant:v1.12.0

# Check logs
docker logs qdrant-serin
```

**Configuration Check:**
```bash
# Verify port availability
netstat -tlnp | grep 6333

# Test connection
curl http://localhost:6333/
```

#### Problem: Qdrant Connection Timeouts
**Symptoms:**
- Connection timeout errors
- Slow response times
- "Connection refused" errors

**Solutions:**
```python
# Test connection with timeout
import qdrant_client
from qdrant_client import QdrantClient

try:
    client = QdrantClient(
        host="localhost",
        port=6333,
        timeout=30,
        connection_retries=3
    )
    # Test connection
    client.get_cluster_info()
    print("✅ Qdrant connection successful")
except Exception as e:
    print(f"❌ Connection failed: {e}")
```

**Environment Variables:**
```bash
# Update .env file
echo "QDRANT_HOST=localhost" >> .env
echo "QDRANT_PORT=6333" >> .env
echo "QDRANT_TIMEOUT=30" >> .env
```

### Memory System Issues

#### Problem: QdrantMemorySystem Initialization Fails
**Symptoms:**
- ImportError for qdrant_client
- Module not found errors
- Connection errors during initialization

**Solutions:**
```bash
# Install missing dependencies
pip install qdrant-client sentence-transformers rank-bm25

# Verify installation
python -c "import qdrant_client; print('Qdrant client available')"
python -c "from sentence_transformers import SentenceTransformer; print('Sentence transformers available')"
```

**Fallback to ChromaDB:**
```python
# In discord_bot.py
try:
    from qdrant_memory_system import QdrantMemorySystem
    memory_system = QdrantMemorySystem()
except ImportError:
    from memory_system import UnifiedMemorySystem
    memory_system = UnifiedMemorySystem()
    logger.warning("⚠️ Qdrant not available, using ChromaDB fallback")
```

#### Problem: Memory Addition Fails
**Symptoms:**
- "Memory not added" errors
- Empty memory IDs
- Embedding generation errors

**Debug Steps:**
```python
# Test memory addition step by step
from qdrant_memory_system import QdrantMemorySystem

memory_system = QdrantMemorySystem()

# Test embedding generation
try:
    embeddings = memory_system.embedding_model.encode(["test message"])
    print("✅ Embedding generation works")
except Exception as e:
    print(f"❌ Embedding failed: {e}")

# Test Qdrant connection
try:
    memory_system.qdrant_client.get_collection("memories")
    print("✅ Qdrant connection works")
except Exception as e:
    print(f"❌ Qdrant connection failed: {e}")
```

**Memory Addition Debug:**
```python
# Add memory with detailed logging
try:
    memory_id = memory_system.add_memory_enhanced(
        content="Test message",
        user_id="test_user",
        username="TestUser",
        channel_id="test_channel",
        participants=["test_user"],
        emotional_tone="neutral",
        importance=0.5,
        source_message_id="test_message_123"
    )
    print(f"✅ Memory added: {memory_id}")
except Exception as e:
    print(f"❌ Memory addition failed: {e}")
    import traceback
    traceback.print_exc()
```

### Search Performance Issues

#### Problem: Slow Search Response Times
**Symptoms:**
- Search queries taking >500ms
- High CPU usage
- Memory spikes

**Solutions:**
```python
# Optimize Qdrant configuration
hnsw_config = {
    "m": 16,  # Graph connectivity
    "ef_construct": 512,  # Index construction quality
    "ef_search": 100  # Query time accuracy
}

# Test with different parameters
results = memory_system.qdrant_client.search(
    collection_name="memories",
    query_vector=query_embedding,
    query_filter=filter,
    limit=10,
    search_params={"ef": 50}  # Lower for faster search
)
```

**BM25 Optimization:**
```python
# Optimize BM25 parameters
bm25_params = {
    "k1": 1.2,  # Term saturation
    "b": 0.75,  # Document length normalization
    "delta": 0.5  # Term frequency normalization
}

# Test with different weights
hybrid_results = memory_system.search_hybrid(
    query="test query",
    user_id="user123",
    n_results=10,
    bm25_weight=0.3,  # Lower for vector-heavy search
    vector_weight=0.7  # Higher for semantic search
)
```

#### Problem: Poor Search Relevance
**Symptoms:**
- Irrelevant search results
- Missing important memories
- Low result scores

**Debug Steps:**
```python
# Test search with different queries
test_queries = [
    "programming",
    "hello world",
    "user conversation",
    "technical discussion"
]

for query in test_queries:
    results = memory_system.search_hybrid(query, "user123", 5)
    print(f"Query: {query}")
    print(f"Results: {len(results)}")
    for result in results:
        print(f"  Score: {result['score']:.3f}")
        print(f"  Text: {result['payload']['text'][:50]}...")
    print()
```

**Reranking Debug:**
```python
# Test reranking functionality
if hasattr(memory_system, 'reranker'):
    test_texts = [
        "This is about programming",
        "Hello world greeting",
        "Technical discussion about AI"
    ]
    
    rerank_scores = memory_system.reranker.rerank("programming", test_texts)
    print("Rerank scores:", rerank_scores)
```

### Integration Issues

#### Problem: Discord Bot Not Starting
**Symptoms:**
- Bot fails to initialize
- Memory system import errors
- Configuration errors

**Debug Steps:**
```python
# Test memory system initialization
try:
    from qdrant_memory_system import QdrantMemorySystem
    memory_system = QdrantMemorySystem()
    print("✅ Qdrant memory system initialized")
except Exception as e:
    print(f"❌ Memory system failed: {e}")

# Test message manager
try:
    from enhanced_message_manager import EnhancedMessageManagerV3
    manager = EnhancedMessageManagerV3(client, mention_translator, memory_system)
    print("✅ Message manager initialized")
except Exception as e:
    print(f"❌ Message manager failed: {e}")
```

**Configuration Debug:**
```python
# Test configuration loading
import os
from dotenv import load_dotenv

load_dotenv()

print("Configuration:")
print(f"USE_QDRANT: {os.getenv('USE_QDRANT')}")
print(f"QDRANT_HOST: {os.getenv('QDRANT_HOST')}")
print(f"QDRANT_PORT: {os.getenv('QDRANT_PORT')}")
print(f"DATA_DIR: {os.getenv('DATA_DIR')}")
```

#### Problem: Control Panel Not Working
**Symptoms:**
- Web interface not loading
- API endpoints returning errors
- WebSocket connection issues

**Debug Steps:**
```bash
# Test API endpoints
curl http://localhost:8080/api/status
curl http://localhost:8080/api/stats
curl -X POST http://localhost:8080/api/search -H "Content-Type: application/json" -d '{"query": "test"}'
```

**WebSocket Debug:**
```javascript
// Test WebSocket connection in browser console
const ws = new WebSocket('ws://localhost:8080/ws');
ws.onmessage = function(event) {
    console.log('Received:', JSON.parse(event.data));
};
ws.onopen = function() {
    console.log('WebSocket connected');
};
ws.onerror = function(error) {
    console.error('WebSocket error:', error);
};
```

### Performance Optimization

#### Problem: High Memory Usage
**Symptoms:**
- RAM usage >16GB
- System slowdown
- Qdrant performance degradation

**Solutions:**
```python
# Enable on-disk storage
qdrant_config = {
    "vectors_config": {
        "size": 768,
        "distance": "Cosine",
        "on_disk": True  # Enable on-disk storage
    },
    "optimizers_config": {
        "default_segment_number": 4,
        "indexing_threshold": 20000,
        "flush_interval_sec": 10
    }
}

# Enable quantization
quantization_config = {
    "scalar": {
        "type": "INT8",
        "quantile": 0.995  # Preserve 99.5% of vector information
    }
}
```

**Memory Cleanup:**
```python
# Automated cleanup
cleaned_count = memory_system.cleanup_old_memories(
    days_old=90,
    min_importance=0.3
)
print(f"Cleaned {cleaned_count} old memories")
```

#### Problem: Slow Ingestion Rate
**Symptoms:**
- Memory addition taking >1 second
- High CPU usage
- Queue buildup

**Solutions:**
```python
# Batch processing
async def batch_add_memories(messages):
    """Add multiple memories in batch"""
    batch_size = 32
    results = []
    
    for i in range(0, len(messages), batch_size):
        batch = messages[i:i + batch_size]
        batch_results = await asyncio.gather(*[
            memory_system.add_memory_enhanced(**msg) for msg in batch
        ])
        results.extend(batch_results)
    
    return results

# Use background jobs
memory_system.queue_background_job(
    job_type="batch_ingestion",
    payload={"messages": message_batch}
)
```

### Data Recovery

#### Problem: Data Corruption
**Symptoms:**
- Memory system errors
- Missing data
- Inconsistent state

**Recovery Steps:**
```bash
# Restore from backup
backup_path="./bot_data/backups/pre_qdrant_migration_20250101_120000"

# Restore Qdrant data
cp -r "$backup_path/qdrant_data" "./bot_data/"

# Restore SQLite database
cp "$backup_path/bot_data.db" "./bot_data/"

# Restore configuration
cp "$backup_path/.env" "./"
```

**Data Verification:**
```python
# Verify data integrity
try:
    stats = memory_system.get_stats()
    print(f"Total memories: {stats['total_memories']}")
    print(f"Total users: {stats['total_users']}")
    
    # Test search
    results = memory_system.search_hybrid("test", None, 5)
    print(f"Search working: {len(results)} results")
    
except Exception as e:
    print(f"Data integrity check failed: {e}")
```

### Monitoring and Logging

#### Problem: Insufficient Logging
**Symptoms:**
- No visibility into system issues
- Difficult debugging
- Performance problems

**Enhanced Logging:**
```python
import logging
from datetime import datetime

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_data/logs/qdrant_migration.log'),
        logging.StreamHandler()
    ]
)

# Memory system logging
logger = logging.getLogger('qdrant_memory')

def log_memory_operation(operation, details):
    logger.info(f"Memory {operation}: {details}")

# Usage
log_memory_operation("add", {"user_id": "123", "content_length": 100})
```

**Performance Monitoring:**
```python
import time
from functools import wraps

def monitor_performance(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        duration = time.time() - start_time
        
        logger.info(f"{func.__name__} took {duration:.3f}s")
        return result
    return wrapper

# Usage
@monitor_performance
async def add_memory_enhanced(self, **kwargs):
    # Memory addition logic
    pass
```

### Common Error Messages and Solutions

#### Error: "qdrant_client not found"
**Solution:**
```bash
pip install qdrant-client
```

#### Error: "SentenceTransformer not found"
**Solution:**
```bash
pip install sentence-transformers
```

#### Error: "Connection refused to localhost:6333"
**Solution:**
```bash
# Start Qdrant container
docker run -d --name qdrant-serin -p 6333:6333 qdrant/qdrant:v1.12.0

# Check status
docker logs qdrant-serin
```

#### Error: "Memory limit exceeded"
**Solution:**
```python
# Increase memory limit or optimize
memory_system.cleanup_old_memories(days_old=30, min_importance=0.2)
```

#### Error: "Embedding generation failed"
**Solution:**
```python
# Test embedding model
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(["test"])
```

### Performance Tuning Guide

#### Qdrant Configuration Tuning
```python
# High-performance configuration
hnsw_config = {
    "m": 32,  # Higher connectivity
    "ef_construct": 1024,  # Better index quality
    "ef_search": 200  # Better search quality
}

# Memory optimization
optimizers_config = {
    "default_segment_number": 8,  # More segments
    "indexing_threshold": 10000,  # Index sooner
    "flush_interval_sec": 5,  # More frequent flush
    "max_optimization_threads": 8  # More threads
}
```

#### Search Optimization
```python
# Hybrid search tuning
search_params = {
    "bm25_weight": 0.4,  # 40% keyword search
    "vector_weight": 0.6,  # 60% semantic search
    "reranking": True,  # Enable reranking
    "reranking_top_k": 50  # Rerank top 50 results
}

# Query optimization
def optimize_query(query):
    """Optimize query for better search results"""
    # Remove common words
    stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at"}
    words = [w for w in query.lower().split() if w not in stop_words]
    return " ".join(words)
```

### Emergency Procedures

#### System Crash Recovery
```bash
# Emergency restart script
#!/bin/bash
echo "🚨 Emergency restart procedure"

# Stop all services
pkill -f "python3 -m serin"
pkill -f "python3 enhanced_api_routes.py"

# Check Qdrant
if ! curl -s http://localhost:6333/ >/dev/null; then
    echo "🔄 Restarting Qdrant..."
    docker restart qdrant-serin
    sleep 10
fi

# Start services
echo "🤖 Starting Discord bot..."
nohup python3 -m serin > logs/bot.log 2>&1 &

echo "🌐 Starting control panel..."
nohup python3 enhanced_api_routes.py > logs/control_panel.log 2>&1 &

echo "✅ Emergency restart complete"
```

#### Data Recovery Procedure
```bash
#!/bin/bash
echo "🔄 Data recovery procedure"

# Latest backup
BACKUP_DIR="./bot_data/backups"
LATEST_BACKUP=$(ls -t $BACKUP_DIR | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ No backups found"
    exit 1
fi

echo "📁 Using backup: $LATEST_BACKUP"

# Stop services
pkill -f "python3 -m serin"
pkill -f "python3 enhanced_api_routes.py"

# Backup current state
cp -r ./bot_data ./bot_data/$(date +%Y%m%d_%H%M%S)_pre_recovery

# Restore from backup
cp -r "$BACKUP_DIR/$LATEST_BACKUP/qdrant_data" ./bot_data/
cp "$BACKUP_DIR/$LATEST_BACKUP/bot_data.db" ./bot_data/

# Start services
echo "🤖 Starting Discord bot..."
python3 -m serin

echo "🌐 Starting control panel..."
python3 enhanced_api_routes.py

echo "✅ Recovery complete"
```

---

## Support Resources

### Documentation
- [Qdrant Official Documentation](https://qdrant.tech/documentation/)
- [Sentence Transformers Documentation](https://www.sbert.net/)
- [Discord.py Documentation](https://discordpy.readthedocs.io/)

### Community Support
- [Qdrant Discord Server](https://discord.gg/qdrant)
- [Python Discord Server](https://discord.gg/python)
- [Stack Overflow](https://stackoverflow.com/)

### Professional Support
- **Enterprise Support**: Contact Qdrant for commercial support
- **Development Support**: Available for custom implementations
- **Consulting**: Available for performance optimization

---

*This troubleshooting guide should be updated regularly based on real-world issues encountered during deployment and operation.*