# Qdrant Migration Plan: Complete Database Replacement

## Executive Summary

This document outlines a comprehensive migration plan to completely replace the existing ChromaDB-based memory system with a Qdrant-based architecture. The approach involves complete database replacement rather than migration, allowing for a clean slate with optimized Qdrant configuration. The migration will enhance performance, scalability, and search accuracy while maintaining all existing functionality and updating the control panel with proper Qdrant-specific controls.

## Current System Analysis

### Architecture Overview
- **Current**: ChromaDB (semantic search) + SQLite (structured data)
- **Target**: Qdrant (vector + payload storage) + External BM25 + Redis/RQ (background processing)

### Key Components to Replace
1. **UnifiedMemorySystem** (`memory_system.py`) → **QdrantMemorySystem**
2. **EnhancedMemoryRetriever** (`enhanced_memory_retrieval.py`) → **HybridMemoryRetriever**
3. **BackgroundProcessor** (`background_processor.py`) → **EnhancedBackgroundProcessor**
4. **Web API endpoints** - Update for Qdrant operations
5. **Control Panel** - Add Qdrant-specific controls and monitoring
6. **Data model** - Redesign for Qdrant payload structure

## Phase 1: Architecture Design & Data Model

### 1.1 Qdrant Collection Architecture

**Single Collection Strategy (Option A)**
```python
# Collection: "memories"
{
    "text": "<raw chunk text>",
    "person_id": "user:12345",
    "person_display": "Anuamba", 
    "timestamp": "2025-11-20T12:34:56Z",
    "last_accessed": "2025-11-25T10:00:00Z",
    "importance": 0.72,
    "channel_id": "discord:server-1.channel-2",
    "conversation_id": "conv-uuid",
    "source_message_id": "discord-msg-uuid",
    "memory_type": "utterance|event|profile|system",
    "topics": ["minecraft","anime"],
    "summary_extract": "short extractive summary...",
    "summary_abstract": "abstractive summary...",
    "embedding_model": "nomic-embed-text-v1.5",
    "embedding_dim": 768,
    "embedding_version": "v1",
    "parent_id": "parent-uuid",
    "linked_ids": ["mem-uuid-x","mem-uuid-y"]
}
```

### 1.2 ID Generation Strategy
```python
import hashlib
import uuid

def generate_memory_id(source_message_id: str, chunk_index: int = 0) -> str:
    """Generate deterministic ID for idempotent ingestion"""
    if source_message_id:
        # Use SHA256 hash for deterministic IDs
        hash_obj = hashlib.sha256(f"{source_message_id}:{chunk_index}".encode())
        return f"mem_{hash_obj.hexdigest()[:16]}"
    else:
        # Fallback to UUID for non-message memories
        return f"mem_{uuid.uuid4().hex[:16]}"
```

### 1.3 New Database Schema (SQLite Only for Structured Data)
Since we're replacing ChromaDB completely, SQLite will only handle structured data:

```sql
-- User profiles (keep existing structure)
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT,
    total_messages INTEGER DEFAULT 0,
    avg_message_length REAL DEFAULT 0,
    personality_traits TEXT,  -- JSON array
    interests TEXT,  -- JSON array
    communication_style TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Relationships (keep existing structure)
CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_a_id TEXT NOT NULL,
    user_b_id TEXT NOT NULL,
    interaction_count INTEGER DEFAULT 0,
    direct_mentions INTEGER DEFAULT 0,
    relationship_strength REAL DEFAULT 0.0,
    last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Activity logs (keep existing structure)
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- NEW: BM25 Search Index (SQLite FTS)
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    id,
    text,
    person_id,
    channel_id,
    memory_type,
    content=memories,
    content_rowid=id
);

-- NEW: Background Job Queue
CREATE TABLE IF NOT EXISTS background_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    memory_id TEXT,
    payload TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0
);

-- NEW: Qdrant Collection Metadata
CREATE TABLE IF NOT EXISTS qdrant_collections (
    collection_name TEXT PRIMARY KEY,
    vector_size INTEGER NOT NULL,
    distance_metric TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active'
);

-- NEW: Memory Statistics
CREATE TABLE IF NOT EXISTS memory_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    total_memories INTEGER DEFAULT 0,
    total_embeddings INTEGER DEFAULT 0,
    avg_embedding_size REAL DEFAULT 0,
    search_count INTEGER DEFAULT 0,
    ingestion_count INTEGER DEFAULT 0,
    UNIQUE(date)
);
```

## Phase 2: Ingestion Pipeline Design

### 2.1 Enhanced Memory Ingestion

```python
class QdrantMemorySystem:
    def __init__(self, data_dir: str = "./bot_data"):
        # Qdrant client
        self.qdrant_client = QdrantClient(":memory:")
        self.qdrant_client.set_model("nomic-embed-text-v1.5")
        
        # BM25 index
        self.bm25_index = SQLiteBM25Index(os.path.join(data_dir, "memory_fts.db"))
        
        # Job queue
        self.job_queue = RedisRQQueue()
        
        # Embedding service
        self.embedding_service = NomicEmbeddingService()
        
        # Collection setup
        self._setup_collection()
    
    def add_memory_enhanced(self, content: str, user_id: str, **kwargs) -> str:
        """Enhanced memory ingestion with chunking and idempotency"""
        
        # 1. Deduplication check
        if self._is_duplicate(content, user_id, kwargs.get('source_message_id')):
            return self._get_existing_memory_id(content, user_id)
        
        # 2. Content chunking
        chunks = self._chunk_content(content, min_tokens=200, max_tokens=600)
        
        # 3. Generate embeddings
        embeddings = self.embedding_service.embed(chunks)
        
        # 4. Batch upsert to Qdrant
        memory_ids = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            memory_id = generate_memory_id(kwargs.get('source_message_id'), i)
            
            payload = self._build_payload(chunk, user_id, i, len(chunks), **kwargs)
            
            self.qdrant_client.upsert(
                collection_name="memories",
                points=[PointStruct(
                    id=memory_id,
                    vector=embedding.tolist(),
                    payload=payload
                )]
            )
            
            # Add to BM25 index
            self.bm25_index.add_document(memory_id, chunk, user_id, kwargs.get('channel_id'))
            
            memory_ids.append(memory_id)
        
        # 5. Queue background jobs
        self._queue_background_jobs(memory_ids, kwargs)
        
        return memory_ids[0] if memory_ids else None
```

### 2.2 Background Job System

```python
class BackgroundJobProcessor:
    JOB_TYPES = {
        'summarize': self._summarize_memory,
        'rerank': self._rerank_memory,
        'prune': self._prune_old_memories,
        'reindex': self._recompute_embeddings
    }
    
    async def process_jobs(self):
        """Process background jobs from queue"""
        while True:
            job = self.job_queue.get_next_job()
            if not job:
                await asyncio.sleep(5)
                continue
            
            try:
                await self.JOB_TYPES[job.job_type](job)
                job.mark_completed()
            except Exception as e:
                job.mark_failed(str(e))
                logger.error(f"Job failed: {e}")
```

## Phase 3: Hybrid Search Architecture

### 3.1 Multi-Stage Search Pipeline

```python
class HybridMemoryRetriever:
    def __init__(self, memory_system):
        self.memory_system = memory_system
        self.reranker = CrossEncoderReranker()
        self.deduplicator = ContentDeduplicator()
    
    def search_hybrid(self, query: str, user_id: str, **filters) -> List[Dict]:
        """Hybrid search: BM25 + Vector + Rerank"""
        
        # Stage 1: BM25 keyword search
        bm25_candidates = self._bm25_search(query, user_id, filters)
        
        # Stage 2: Vector semantic search  
        vector_candidates = self._vector_search(query, user_id, filters)
        
        # Stage 3: Merge and deduplicate
        merged_candidates = self._merge_candidates(bm25_candidates, vector_candidates)
        
        # Stage 4: Rerank top candidates
        reranked_results = self._rerank_results(query, merged_candidates)
        
        # Stage 5: Condense and return
        return self._condense_results(reranked_results)
    
    def _bm25_search(self, query: str, user_id: str, filters: Dict) -> List[Dict]:
        """External BM25 search using SQLite FTS"""
        return self.memory_system.bm25_index.search(
            query=query,
            user_id=user_id,
            channel_id=filters.get('channel_id'),
            limit=20
        )
    
    def _vector_search(self, query: str, user_id: str, filters: Dict) -> List[Dict]:
        """Qdrant vector search with payload filtering"""
        # Build Qdrant filter
        qdrant_filter = self._build_qdrant_filter(user_id, filters)
        
        # Generate query embedding
        query_embedding = self.memory_system.embedding_service.embed([query])[0]
        
        # Search Qdrant
        results = self.memory_system.qdrant_client.search(
            collection_name="memories",
            query_vector=query_embedding.tolist(),
            query_filter=qdrant_filter,
            limit=50
        )
        
        return [{'id': r.id, 'score': r.score, 'payload': r.payload} for r in results]
    
    def _rerank_results(self, query: str, candidates: List[Dict], top_k: int = 30) -> List[Dict]:
        """Cross-encoder reranking"""
        if len(candidates) <= top_k:
            return candidates
        
        # Extract texts for reranking
        texts = [c['payload']['text'] for c in candidates[:top_k]]
        
        # Rerank using cross-encoder
        reranked_scores = self.reranker.rerank(query, texts)
        
        # Apply reranked scores
        for i, candidate in enumerate(candidates[:top_k]):
            candidate['rerank_score'] = reranked_scores[i]
        
        # Sort by rerank score
        return sorted(candidates[:top_k], key=lambda x: x['rerank_score'], reverse=True)
```

### 3.2 Qdrant Filter Construction

```python
def _build_qdrant_filter(self, user_id: str, filters: Dict) -> Filter:
    """Build Qdrant payload filter"""
    
    conditions = []
    
    # User filter
    if user_id:
        conditions.append(FieldCondition(key="person_id", match=MatchValue(value=user_id)))
    
    # Channel filter
    if filters.get('channel_id'):
        conditions.append(FieldCondition(key="channel_id", match=MatchValue(value=filters['channel_id'])))
    
    # Time range filter
    if filters.get('start_time'):
        conditions.append(Range(key="timestamp", gte=filters['start_time']))
    
    if filters.get('end_time'):
        conditions.append(Range(key="timestamp", lte=filters['end_time']))
    
    # Importance filter
    if filters.get('min_importance'):
        conditions.append(Range(key="importance", gte=filters['min_importance']))
    
    # Memory type filter
    if filters.get('memory_type'):
        conditions.append(FieldCondition(key="memory_type", match=MatchValue(value=filters['memory_type'])))
    
    return Filter(must=conditions)
```

## Phase 4: Performance Optimization

### 4.1 Qdrant Configuration for 1M+ Vectors

```python
def setup_qdrant_collection():
    """Optimized Qdrant configuration for large-scale deployment"""
    
    hnsw_config = HnswConfig(
        m=16,  # Graph connectivity - balance between recall and speed
        ef_construct=512,  # Higher quality index construction
        ef_search=100  # Query time accuracy (can be adjusted per query)
    )
    
    quantization_config = QuantizationConfig(
        scalar=ScalarQuantizationConfig(
            type=ScalarQuantizationType.INT8,
            quantile=0.995  # Preserve 99.5% of vector information
        )
    )
    
    # Create collection with optimized settings
    client.recreate_collection(
        collection_name="memories",
        vectors_config=VectorParams(
            size=768,  # Nomic embedding dimension
            distance=Distance.COSINE,
            on_disk=True  # Enable on-disk storage for memory efficiency
        ),
        hnsw_config=hnsw_config,
        quantization_config=quantization_config,
        optimizers_config=OptimizersConfig(
            default_segment_number=4,  # Parallel optimization
            indexing_threshold=20000,  # When to start indexing
            flush_interval_sec=10,  # How often to flush to disk
            max_optimization_threads=4
        ),
        wal_config=WalConfig(
            wal_capacity_mb=32,  # Write-Ahead Log size
            wal_segments_ahead=0
        )
    )
```

### 4.2 Memory Management

```python
class MemoryManager:
    def __init__(self, memory_system):
        self.memory_system = memory_system
        self.retention_policy = {
            'default_retention_days': 90,
            'high_importance_retention_days': 365,
            'low_importance_threshold': 0.3,
            'prune_batch_size': 1000
        }
    
    async def cleanup_old_memories(self):
        """Automated memory cleanup with smart retention"""
        
        cutoff_date = datetime.now() - timedelta(days=self.retention_policy['default_retention_days'])
        
        # Find old, low-importance memories
        old_memories = self.memory_system.qdrant_client.scroll(
            collection_name="memories",
            scroll_filter=Filter(
                must=[
                    Range(key="timestamp", lt=cutoff_date.isoformat()),
                    Range(key="importance", lt=self.retention_policy['low_importance_threshold'])
                ]
            ),
            limit=self.retention_policy['prune_batch_size']
        )
        
        # Batch delete
        if old_memories:
            memory_ids = [m.id for m in old_memories]
            self.memory_system.qdrant_client.delete(
                collection_name="memories",
                points_selector=ids_selector(memory_ids)
            )
            
            # Also clean up BM25 index
            self.memory_system.bm25_index.delete_documents(memory_ids)
            
            logger.info(f"Pruned {len(memory_ids)} old memories")
```

## Phase 5: Monitoring & Observability

### 5.1 Metrics Collection

```python
class MemoryMetrics:
    def __init__(self):
        self.metrics = {
            'ingestion_count': 0,
            'ingestion_errors': 0,
            'search_count': 0,
            'search_latency': [],
            'memory_size': 0,
            'qdrant_health': 'unknown',
            'bm25_health': 'unknown'
        }
    
    def track_ingestion(self, success: bool, duration: float):
        self.metrics['ingestion_count'] += 1
        if not success:
            self.metrics['ingestion_errors'] += 1
    
    def track_search(self, duration: float):
        self.metrics['search_count'] += 1
        self.metrics['search_latency'].append(duration)
        
        # Keep only last 100 measurements
        if len(self.metrics['search_latency']) > 100:
            self.metrics['search_latency'] = self.metrics['search_latency'][-100:]
    
    def get_health_status(self) -> Dict:
        """Overall system health assessment"""
        
        avg_search_latency = np.mean(self.metrics['search_latency']) if self.metrics['search_latency'] else 0
        
        health_score = 100
        
        # Deduct points for various issues
        if avg_search_latency > 1000:  # > 1s average search time
            health_score -= 20
        
        error_rate = self.metrics['ingestion_errors'] / max(1, self.metrics['ingestion_count'])
        if error_rate > 0.05:  # > 5% error rate
            health_score -= 30
        
        return {
            'health_score': health_score,
            'status': 'healthy' if health_score > 80 else 'degraded' if health_score > 50 else 'critical',
            'avg_search_latency': avg_search_latency,
            'error_rate': error_rate,
            'memory_size': self.metrics['memory_size']
        }
```

### 5.2 Backup Strategy

```python
class BackupManager:
    def __init__(self, memory_system):
        self.memory_system = memory_system
        self.backup_dir = "./bot_data/backups"
        os.makedirs(self.backup_dir, exist_ok=True)
    
    async def create_backup(self, backup_type: str = "manual") -> str:
        """Create comprehensive backup of Qdrant + SQLite data"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.backup_dir, f"backup_{timestamp}_{backup_type}")
        
        try:
            # 1. Qdrant snapshot
            qdrant_snapshot = await self._backup_qdrant(backup_path)
            
            # 2. SQLite databases
            sqlite_backups = await self._backup_sqlite(backup_path)
            
            # 3. Configuration files
            config_backup = await self._backup_config(backup_path)
            
            # 4. Create manifest
            manifest = {
                'timestamp': timestamp,
                'backup_type': backup_type,
                'qdrant_snapshot': qdrant_snapshot,
                'sqlite_backups': sqlite_backups,
                'config_backup': config_backup,
                'memory_count': self.memory_system.get_stats()['total_memories']
            }
            
            with open(os.path.join(backup_path, 'manifest.json'), 'w') as f:
                json.dump(manifest, f, indent=2)
            
            logger.info(f"✅ Backup created: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
            raise
    
    async def restore_backup(self, backup_path: str) -> bool:
        """Restore from backup"""
        
        try:
            # Load manifest
            with open(os.path.join(backup_path, 'manifest.json'), 'r') as f:
                manifest = json.load(f)
            
            # 1. Restore Qdrant
            await self._restore_qdrant(backup_path, manifest['qdrant_snapshot'])
            
            # 2. Restore SQLite
            await self._restore_sqlite(backup_path, manifest['sqlite_backups'])
            
            logger.info(f"✅ Restore completed from: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Restore failed: {e}")
            return False
```

## Phase 6: Implementation Roadmap

### Sprint 1: Foundation (Week 1-2)
- [ ] Set up Qdrant instance and basic configuration
- [ ] Implement data model mapping and ID generation
- [ ] Create basic ingestion pipeline
- [ ] Set up BM25 index with SQLite FTS
- [ ] Implement basic search functionality

### Sprint 2: Enhanced Features (Week 3-4)
- [ ] Implement hybrid search pipeline
- [ ] Add cross-encoder reranking
- [ ] Create background job system
- [ ] Implement memory deduplication
- [ ] Add content chunking logic

### Sprint 3: Performance Optimization (Week 5-6)
- [ ] Optimize Qdrant for 1M+ vectors
- [ ] Implement quantization and on-disk storage
- [ ] Add memory cleanup and pruning
- [ ] Implement caching layer
- [ ] Performance testing and tuning

### Sprint 4: Advanced Features (Week 7-8)
- [ ] Implement monitoring and metrics
- [ ] Create backup and restore system
- [ ] Add web API endpoints for Qdrant operations
- [ ] Implement health checks and alerts
- [ ] Documentation and testing

## Success Criteria

### Technical Metrics
- **Search Performance**: <100ms average query response time
- **Ingestion Rate**: >1000 memories/minute
- **Memory Efficiency**: <16GB RAM for 1M vectors
- **Availability**: 99.9% uptime
- **Data Integrity**: Zero data loss during migration

### Functional Requirements
- **Backward Compatibility**: All existing ChromaDB functionality preserved
- **Search Quality**: Hybrid search improves relevance by 20%+
- **Scalability**: Support 10M+ memories without performance degradation
- **Reliability**: Automatic recovery from failures
- **Maintainability**: Clear monitoring and debugging capabilities

## Risk Mitigation

### High-Risk Areas
1. **Data Loss Risk**
   - Mitigation: Complete backup of existing system before replacement
   - Recovery: Full system restore from backup

2. **Performance Degradation**
   - Mitigation: Load testing and gradual rollout
   - Recovery: Performance monitoring and auto-scaling

3. **Search Quality Impact**
   - Mitigation: A/B testing search algorithms
   - Recovery: Algorithm parameter tuning and optimization

4. **Control Panel Compatibility**
   - Mitigation: Progressive enhancement of UI components
   - Recovery: Maintain backward compatibility during transition

### Rollback Strategy
1. **Complete System Backup**: Full backup of ChromaDB, SQLite, and configuration
2. **Clean Slate Migration**: No data migration - fresh Qdrant instance
3. **Gradual Rollout**: Test with limited channels/users first
4. **Monitoring**: Real-time performance comparison with baseline
5. **Emergency Restore**: Quick restoration from backup if needed

### Data Migration Approach
Since we're replacing the database completely:
1. **Stop all services** and create complete backup
2. **Uninstall ChromaDB** dependencies and remove data files
3. **Install Qdrant** and configure for production
4. **Initialize new schema** in SQLite (structured data only)
5. **Start services** with fresh Qdrant instance
6. **Begin new data ingestion** through Discord messages

## Conclusion

This migration plan provides a comprehensive approach to completely replacing the ChromaDB-based memory system with a Qdrant-based architecture. The clean slate approach eliminates migration complexity while allowing for optimized Qdrant configuration from the start.

The hybrid architecture combines the strengths of vector search, keyword search, and advanced reranking to deliver superior memory retrieval capabilities. The enhanced control panel provides comprehensive monitoring and management tools for the new Qdrant-based system.

The phased implementation approach ensures manageable risk while allowing for continuous improvement and optimization throughout the migration process, with complete control panel integration for enhanced user experience.