"""
Qdrant Memory System - Complete replacement for ChromaDB
Implements hybrid search with BM25 + Vector + Reranking
"""
import os
import json
import sqlite3
import hashlib
import uuid
import asyncio
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from thinking_filter import filter_for_memory
from logger_config import logger
from debug_logger import log_memory

# Qdrant imports
try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
    from qdrant_client.http.models import Distance, VectorParams, HnswConfig, OptimizersConfig, WalConfig, QuantizationConfig, ScalarQuantizationConfig, ScalarQuantization
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("Qdrant not available - falling back to mock implementation")

# Embedding service
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    logger.warning("Sentence transformers not available")

# BM25 implementation
try:
    import rank_bm25
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    logger.warning("Rank BM25 not available")


class QdrantMemorySystem:
    def __init__(self, data_dir: str = "./bot_data", qdrant_host: str = "localhost", qdrant_port: int = 6333):
        """Initialize Qdrant-based memory system with hybrid search capabilities"""
        logger.info("🚀 Initializing Qdrant Memory System")
        
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize Qdrant client
        if QDRANT_AVAILABLE:
            try:
                self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
                logger.info(f"✅ Qdrant client connected to {qdrant_host}:{qdrant_port}")
            except Exception as e:
                logger.error(f"❌ Failed to connect to Qdrant: {e}")
                self.qdrant_client = None
        else:
            self.qdrant_client = None
        
        # Initialize embedding service
        if EMBEDDING_AVAILABLE:
            try:
                # Upgrade to Nomic Embed v1.5 for state-of-the-art performance
                self.embedding_model = SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)
                self.embedding_dim = 768  # Nomic dimension
                logger.info("✅ Nomic Embed v1.5 model loaded (High Quality)")
            except Exception as e:
                logger.error(f"❌ Failed to load embedding model: {e}")
                self.embedding_model = None
        else:
            self.embedding_model = None
        
        # Initialize BM25 index
        if BM25_AVAILABLE:
            try:
                self.bm25_index = SQLiteBM25Index(os.path.join(data_dir, "memory_fts.db"))
                logger.info("✅ BM25 index initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize BM25: {e}")
                self.bm25_index = None
        else:
            self.bm25_index = None
        
        # Initialize SQLite for structured data
        self.db_path = os.path.join(data_dir, "bot_data.db")
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_sqlite_schema()
        
        # Setup collection if needed
        if self.qdrant_client:
            self._setup_collection()
        
        # Background job queue (simplified implementation)
        self.background_jobs = []
        
        logger.info("✅ Qdrant Memory System ready")
    
    def _init_sqlite_schema(self):
        """Initialize SQLite tables for structured data"""
        cursor = self.conn.cursor()
        
        # User profiles
        cursor.execute("""
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
            )
        """)
        
        # Relationships
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a_id TEXT NOT NULL,
                user_b_id TEXT NOT NULL,
                interaction_count INTEGER DEFAULT 0,
                direct_mentions INTEGER DEFAULT 0,
                relationship_strength REAL DEFAULT 0.0,
                last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_a_id, user_b_id)
            )
        """)
        
        # Activity logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # BM25 Search Index (SQLite FTS)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                id,
                text,
                person_id,
                channel_id,
                memory_type,
                content=memories,
                content_rowid=id
            )
        """)
        
        # Background Job Queue
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS background_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                memory_id TEXT,
                payload TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                priority INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0
            )
        """)
        
        # Qdrant Collection Metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS qdrant_collections (
                collection_name TEXT PRIMARY KEY,
                vector_size INTEGER NOT NULL,
                distance_metric TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)
        
        # Memory Statistics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                total_memories INTEGER DEFAULT 0,
                total_embeddings INTEGER DEFAULT 0,
                avg_embedding_size REAL DEFAULT 0,
                search_count INTEGER DEFAULT 0,
                ingestion_count INTEGER DEFAULT 0,
                UNIQUE(date)
            )
        """)
        
        self.conn.commit()
        logger.debug("✅ SQLite schema initialized")
    
    def _setup_collection(self):
        """Setup Qdrant collection with optimized configuration"""
        if not self.qdrant_client:
            return
        
        try:
            # Check if collection exists
            try:
                self.qdrant_client.get_collection("memories")
                logger.info("✅ Existing memories collection found")
                return
            except:
                pass
            
            # Create collection with optimized settings
            hnsw_config = HnswConfig(
                m=16,  # Graph connectivity
                ef_construct=512,  # Index construction quality
                ef_search=100  # Query time accuracy
            )
            
            quantization_config = QuantizationConfig(
                scalar=ScalarQuantizationConfig(
                    type=ScalarQuantizationType.INT8,
                    quantile=0.995
                )
            )
            
            self.qdrant_client.create_collection(
                collection_name="memories",
                vectors_config=VectorParams(
                    size=self.embedding_dim,
                    distance=Distance.COSINE,
                    on_disk=True
                ),
                hnsw_config=hnsw_config,
                quantization_config=quantization_config,
                optimizers_config=OptimizersConfig(
                    default_segment_number=4,
                    indexing_threshold=20000,
                    flush_interval_sec=10,
                    max_optimization_threads=4
                ),
                wal_config=WalConfig(
                    wal_capacity_mb=32,
                    wal_segments_ahead=0
                )
            )
            
            # Record collection metadata
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO qdrant_collections 
                (collection_name, vector_size, distance_metric, status)
                VALUES (?, ?, ?, ?)
            """, ("memories", self.embedding_dim, "cosine", "active"))
            self.conn.commit()
            
            logger.info("✅ Qdrant collection 'memories' created with optimized settings")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup Qdrant collection: {e}")
    
    def generate_memory_id(self, source_message_id: str, chunk_index: int = 0) -> str:
        """Generate deterministic ID for idempotent ingestion"""
        if source_message_id:
            # Use SHA256 hash for deterministic IDs
            hash_obj = hashlib.sha256(f"{source_message_id}:{chunk_index}".encode())
            return f"mem_{hash_obj.hexdigest()[:16]}"
        else:
            # Fallback to UUID for non-message memories
            return f"mem_{uuid.uuid4().hex[:16]}"
    
    def _chunk_content(self, content: str, min_tokens: int = 200, max_tokens: int = 600) -> List[str]:
        """Split content into appropriate chunks"""
        # Simple chunking by sentences
        sentences = content.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 2 <= max_tokens:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
                
                # Start new chunk if it's already too long
                if len(current_chunk) > max_tokens:
                    chunks.append(current_chunk[:max_tokens])
                    current_chunk = current_chunk[max_tokens:]
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # Ensure minimum chunk size
        if len(chunks) > 1 and len(chunks[0]) < min_tokens:
            # Merge first two chunks
            chunks[1] = chunks[0] + " " + chunks[1]
            chunks.pop(0)
        
        return chunks
    
    def _build_payload(self, content: str, user_id: str, chunk_index: int, total_chunks: int, **kwargs) -> Dict:
        """Build Qdrant payload for memory"""
        return {
            "text": content,
            "person_id": user_id,
            "person_display": kwargs.get('username', ''),
            "timestamp": datetime.now().isoformat(),
            "timestamp_ts": datetime.now().timestamp(),
            "last_accessed": datetime.now().isoformat(),
            "importance": kwargs.get('importance', 0.5),
            "channel_id": kwargs.get('channel_id', ''),
            "conversation_id": kwargs.get('conversation_id', ''),
            "source_message_id": kwargs.get('source_message_id', ''),
            "memory_type": kwargs.get('memory_type', 'utterance'),
            "topics": kwargs.get('topics', []),
            "summary_extract": kwargs.get('summary_extract', ''),
            "summary_abstract": kwargs.get('summary_abstract', ''),
            "embedding_model": "nomic-embed-text-v1.5",
            "embedding_dim": self.embedding_dim,
            "embedding_version": "v1",
            "parent_id": kwargs.get('parent_id', ''),
            "linked_ids": kwargs.get('linked_ids', []),
            "chunk_index": chunk_index,
            "total_chunks": total_chunks
        }
    
    def _is_duplicate(self, content: str, user_id: str, source_message_id: str = None) -> bool:
        """Check if memory already exists"""
        if source_message_id:
            # Check by message ID first
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM background_jobs WHERE memory_id LIKE ? AND job_type = 'dedup'", 
                          (f"%{source_message_id}%",))
            if cursor.fetchone():
                return True
        
        # Simple content-based deduplication (can be enhanced)
        return False
    
    def _get_existing_memory_id(self, content: str, user_id: str) -> str:
        """Get existing memory ID for duplicate content"""
        # This would need to be implemented based on your deduplication strategy
        return None
    
    def _queue_background_jobs(self, memory_ids: List[str], kwargs: Dict):
        """Queue background processing jobs"""
        cursor = self.conn.cursor()
        
        for memory_id in memory_ids:
            # Queue summarization job
            cursor.execute("""
                INSERT INTO background_jobs (job_type, memory_id, payload, priority)
                VALUES (?, ?, ?, ?)
            """, ("summarize", memory_id, json.dumps(kwargs), 1))
            
            # Queue reranking job
            cursor.execute("""
                INSERT INTO background_jobs (job_type, memory_id, payload, priority)
                VALUES (?, ?, ?, ?)
            """, ("rerank", memory_id, json.dumps(kwargs), 2))
        
        self.conn.commit()
    
    def add_memory_enhanced(self, content: str, user_id: str, **kwargs) -> str:
        """Enhanced memory ingestion with chunking and idempotency"""
        content = filter_for_memory(content)
        
        try:
            # 1. Deduplication check
            if self._is_duplicate(content, user_id, kwargs.get('source_message_id')):
                existing_id = self._get_existing_memory_id(content, user_id)
                if existing_id:
                    return existing_id
            
            # 2. Content chunking
            chunks = self._chunk_content(content, min_tokens=200, max_tokens=600)
            
            # 3. Generate embeddings
            embeddings = []
            if self.embedding_model:
                try:
                    # Nomic requires 'search_document: ' prefix for documents
                    prefixed_chunks = [f"search_document: {c}" for c in chunks]
                    chunk_embeddings = self.embedding_model.encode(prefixed_chunks)
                    embeddings = [emb.tolist() for emb in chunk_embeddings]
                except Exception as e:
                    logger.error(f"❌ Error generating embeddings: {e}")
                    # Create zero embeddings as fallback
                    embeddings = [[0.0] * self.embedding_dim for _ in chunks]
            else:
                # Create zero embeddings if model not available
                embeddings = [[0.0] * self.embedding_dim for _ in chunks]
            
            # 4. Batch upsert to Qdrant
            memory_ids = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                memory_id = self.generate_memory_id(kwargs.get('source_message_id'), i)
                
                payload = self._build_payload(chunk, user_id, i, len(chunks), **kwargs)
                
                if self.qdrant_client:
                    try:
                        self.qdrant_client.upsert(
                            collection_name="memories",
                            points=[models.PointStruct(
                                id=memory_id,
                                vector=embedding,
                                payload=payload
                            )]
                        )
                    except Exception as e:
                        logger.error(f"❌ Error upserting to Qdrant: {e}")
                
                # Add to BM25 index
                if self.bm25_index:
                    try:
                        self.bm25_index.add_document(memory_id, chunk, user_id, kwargs.get('channel_id'))
                    except Exception as e:
                        logger.error(f"❌ Error adding to BM25: {e}")
                
                memory_ids.append(memory_id)
            
            # 5. Queue background jobs
            self._queue_background_jobs(memory_ids, kwargs)
            
            # 6. Update statistics
            self._update_ingestion_stats(len(memory_ids))
            
            logger.debug(f"💾 Stored {len(memory_ids)} memory chunks: {content[:50]}...")
            log_memory(content, payload)
            
            return memory_ids[0] if memory_ids else None
            
        except Exception as e:
            logger.error(f"❌ Error adding memory: {e}")
            return None
    
    def search_hybrid(self, query: str, user_id: str = None, n_results: int = 5, **filters) -> List[Dict]:
        """Hybrid search: BM25 + Vector + Rerank"""
        try:
            # Stage 1: BM25 keyword search
            bm25_candidates = []
            if self.bm25_index:
                try:
                    bm25_candidates = self.bm25_index.search(
                        query=query,
                        user_id=user_id,
                        channel_id=filters.get('channel_id'),
                        limit=20
                    )
                except Exception as e:
                    logger.error(f"❌ Error in BM25 search: {e}")
            
            # Stage 2: Vector semantic search  
            vector_candidates = []
            if self.qdrant_client and self.embedding_model:
                try:
                    # Build Qdrant filter
                    qdrant_filter = self._build_qdrant_filter(user_id, filters)
                    
                    # Generate query embedding (Nomic requires 'search_query: ' prefix)
                    query_embedding = self.embedding_model.encode([f"search_query: {query}"])[0].tolist()
                    
                    # Search Qdrant
                    results = self.qdrant_client.search(
                        collection_name="memories",
                        query_vector=query_embedding,
                        query_filter=qdrant_filter,
                        limit=50
                    )
                    
                    vector_candidates = [{'id': r.id, 'score': r.score, 'payload': r.payload} for r in results]
                except Exception as e:
                    logger.error(f"❌ Error in vector search: {e}")
            
            # Stage 3: Merge and deduplicate
            merged_candidates = self._merge_candidates(bm25_candidates, vector_candidates)
            
            # Stage 4: Rerank top candidates (simplified)
            reranked_results = self._rerank_results_simple(query, merged_candidates, n_results)
            
            # Stage 5: Condense and return
            return self._condense_results(reranked_results)
            
        except Exception as e:
            logger.error(f"❌ Error in hybrid search: {e}")
            return []
    
    def _build_qdrant_filter(self, user_id: str, filters: Dict) -> models.Filter:
        """Build Qdrant payload filter"""
        conditions = []
        
        # User filter
        if user_id:
            conditions.append(models.FieldCondition(key="person_id", match=models.MatchValue(value=user_id)))
        
        # Channel filter
        if filters.get('channel_id'):
            conditions.append(models.FieldCondition(key="channel_id", match=models.MatchValue(value=filters['channel_id'])))
        
        # Time range filter (using timestamp_ts)
        if filters.get('start_time'):
            # Convert ISO string to timestamp if needed
            start_ts = filters['start_time']
            if isinstance(start_ts, str):
                try:
                    start_ts = datetime.fromisoformat(start_ts.replace('Z', '+00:00')).timestamp()
                except:
                    pass
            conditions.append(models.FieldCondition(key="timestamp_ts", range=models.Range(gte=start_ts)))
        
        if filters.get('end_time'):
            end_ts = filters['end_time']
            if isinstance(end_ts, str):
                try:
                    end_ts = datetime.fromisoformat(end_ts.replace('Z', '+00:00')).timestamp()
                except:
                    pass
            conditions.append(models.FieldCondition(key="timestamp_ts", range=models.Range(lte=end_ts)))
        
        # Importance filter
        if filters.get('min_importance'):
            conditions.append(models.FieldCondition(key="importance", range=models.Range(gte=filters['min_importance'])))
        
        # Memory type filter
        if filters.get('memory_type'):
            conditions.append(models.FieldCondition(key="memory_type", match=models.MatchValue(value=filters['memory_type'])))
        
        return models.Filter(must=conditions) if conditions else None
    
    def _merge_candidates(self, bm25_candidates: List[Dict], vector_candidates: List[Dict]) -> List[Dict]:
        """Merge results from BM25 and vector search"""
        merged = {}
        
        # Add BM25 candidates
        for candidate in bm25_candidates:
            candidate_id = candidate.get('id')
            if candidate_id:
                merged[candidate_id] = {
                    'id': candidate_id,
                    'bm25_score': candidate.get('score', 0),
                    'vector_score': 0,
                    'payload': candidate.get('payload', {})
                }
        
        # Add vector candidates
        for candidate in vector_candidates:
            candidate_id = candidate.get('id')
            if candidate_id:
                if candidate_id in merged:
                    # Update existing candidate with vector score
                    merged[candidate_id]['vector_score'] = candidate.get('score', 0)
                else:
                    # Add new candidate
                    merged[candidate_id] = {
                        'id': candidate_id,
                        'bm25_score': 0,
                        'vector_score': candidate.get('score', 0),
                        'payload': candidate.get('payload', {})
                    }
        
        # Convert to list and calculate combined score
        result_list = list(merged.values())
        for item in result_list:
            # Combined score: 60% vector + 40% BM25
            item['combined_score'] = (item['vector_score'] * 0.6) + (item['bm25_score'] * 0.4)
        
        return result_list
    
    def _rerank_results_simple(self, query: str, candidates: List[Dict], top_k: int = 30) -> List[Dict]:
        """Simple reranking based on recency and importance"""
        if len(candidates) <= top_k:
            return candidates
        
        # Sort by combined score first
        candidates.sort(key=lambda x: x['combined_score'], reverse=True)
        
        # Take top_k and apply simple reranking
        top_candidates = candidates[:top_k]
        
        # Simple reranking: boost recent and important memories
        for candidate in top_candidates:
            payload = candidate.get('payload', {})
            
            # Recency boost (newer = higher score)
            timestamp = payload.get('timestamp')
            if timestamp:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    age_days = (datetime.now() - dt).days
                    recency_boost = max(0, 1 - (age_days / 365))  # Decay over a year
                    candidate['rerank_score'] = candidate['combined_score'] + (recency_boost * 0.2)
                except:
                    candidate['rerank_score'] = candidate['combined_score']
            else:
                candidate['rerank_score'] = candidate['combined_score']
            
            # Importance boost
            importance = payload.get('importance', 0.5)
            candidate['rerank_score'] += (importance - 0.5) * 0.1
        
        # Sort by rerank score
        top_candidates.sort(key=lambda x: x['rerank_score'], reverse=True)
        
        return top_candidates
    
    def _condense_results(self, results: List[Dict]) -> List[Dict]:
        """Condense results to final format"""
        condensed = []
        
        for result in results:
            payload = result.get('payload', {})
            condensed.append({
                'content': payload.get('text', ''),
                'username': payload.get('person_display', ''),
                'timestamp': payload.get('timestamp', ''),
                'emotional_tone': payload.get('emotional_tone', 'neutral'),
                'relevance': result.get('rerank_score', result.get('combined_score', 0)),
                'age_days': self._calculate_age_days(payload.get('timestamp', '')),
                'channel_id': payload.get('channel_id', ''),
                'participants': payload.get('participants', []),
                'memory_type': payload.get('memory_type', 'utterance'),
                'importance': payload.get('importance', 0.5)
            })
        
        return condensed
    
    def _calculate_age_days(self, timestamp: str) -> int:
        """Calculate age in days from timestamp"""
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return (datetime.now() - dt).days
        except:
            return 0
    
    def _update_ingestion_stats(self, count: int):
        """Update ingestion statistics"""
        from datetime import datetime
        today = datetime.now().date().isoformat()
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO memory_stats 
            (date, total_memories, ingestion_count)
            VALUES (?, COALESCE((SELECT total_memories FROM memory_stats WHERE date = ?), 0) + ?, ?)
        """, (today, today, count, count))
        self.conn.commit()
    
    # ========================================================================
    # Legacy compatibility methods
    # ========================================================================
    
    def add_memory(self, content: str, user_id: str, username: str, channel_id: str, 
                  participants: List[str], emotional_tone: str = "neutral", 
                  importance: float = 0.5, message_id: str = None) -> str:
        """Legacy compatibility method"""
        return self.add_memory_enhanced(
            content=content,
            user_id=user_id,
            username=username,
            channel_id=channel_id,
            participants=participants,
            emotional_tone=emotional_tone,
            importance=importance,
            source_message_id=message_id
        )
    
    def search_memories(self, query: str, user_id: str = None, channel_id: str = None, 
                       n_results: int = 5, time_decay_days: int = 60) -> List[Dict]:
        """Legacy compatibility method"""
        filters = {}
        if channel_id:
            filters['channel_id'] = channel_id
        
        results = self.search_hybrid(query, user_id, n_results, **filters)
        
        # Apply time decay filter
        filtered_results = []
        now = datetime.now()
        
        for result in results:
            age_days = result.get('age_days', 0)
            if age_days <= time_decay_days:
                filtered_results.append(result)
        
        return filtered_results
    
    def get_recent_conversation(self, channel_id: str = None, user_id: str = None, limit: int = 20) -> List[Dict]:
        """Get recent conversation context"""
        try:
            if self.qdrant_client:
                # Build filter
                qdrant_filter = self._build_qdrant_filter(user_id, {'channel_id': channel_id} if channel_id else {})
                
                # Get recent memories
                results = self.qdrant_client.scroll(
                    collection_name="memories",
                    scroll_filter=qdrant_filter,
                    limit=limit * 2
                )
                
                memories = []
                for point in results[0]:  # results[0] contains the points
                    memories.append({
                        'content': point.payload.get('text', ''),
                        'username': point.payload.get('person_display', ''),
                        'timestamp': point.payload.get('timestamp', ''),
                        'user_id': point.payload.get('person_id', '')
                    })
                
                # Sort by timestamp
                memories.sort(key=lambda x: x['timestamp'])
                return memories[-limit:]
            
            return []
            
        except Exception as e:
            logger.error(f"❌ Error getting recent conversation: {e}")
            return []
    
    # ========================================================================
    # User Management (SQLite)
    # ========================================================================
    
    def upsert_user(self, user_id: str, username: str, display_name: str = None):
        """Create or update user profile"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (user_id, username, display_name, last_seen)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    display_name = excluded.display_name,
                    last_seen = CURRENT_TIMESTAMP
            """, (user_id, username, display_name or username))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Error upserting user: {e}")
    
    def update_user_activity(self, user_id: str, message_length: int):
        """Update user activity metrics"""
        cursor = self.conn.cursor()
        try:
            # Get current stats
            cursor.execute("SELECT total_messages, avg_message_length FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            if result:
                total_msgs = result['total_messages']
                avg_len = result['avg_message_length']
                
                new_total = total_msgs + 1
                new_avg = ((avg_len * total_msgs) + message_length) / new_total
                
                cursor.execute("""
                    UPDATE users SET
                        total_messages = ?,
                        avg_message_length = ?,
                        last_seen = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (new_total, new_avg, user_id))
                self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Error updating user activity: {e}")
    
    def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """Get user profile"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result:
            profile = dict(result)
            profile['personality_traits'] = json.loads(profile['personality_traits'] or '[]')
            profile['interests'] = json.loads(profile['interests'] or '[]')
            return profile
        return None
    
    # ========================================================================
    # Stats & Maintenance
    # ========================================================================
    
    def get_stats(self) -> Dict:
        """Get memory system statistics"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM relationships WHERE relationship_strength > 0.5")
            strong_relationships = cursor.fetchone()['count']
            
            # Qdrant memory count
            memory_count = 0
            if self.qdrant_client:
                try:
                    memory_count = self.qdrant_client.count("memories").count
                except:
                    memory_count = 0
            
            return {
                'total_users': total_users,
                'total_memories': memory_count,
                'strong_relationships': strong_relationships,
                'qdrant_connected': self.qdrant_client is not None,
                'embedding_available': self.embedding_model is not None,
                'bm25_available': self.bm25_index is not None
            }
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {}
    
    def cleanup_old_memories(self, days_old: int = 90, min_importance: float = 0.3):
        """Remove old, unimportant memories"""
        try:
            cutoff = (datetime.now() - timedelta(days=days_old)).isoformat()
            
            if self.qdrant_client:
                # Find old, low-importance memories
                old_memories = self.qdrant_client.scroll(
                    collection_name="memories",
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(key="timestamp_ts", range=models.Range(lt=datetime.fromisoformat(cutoff).timestamp())),
                            models.FieldCondition(key="importance", range=models.Range(lt=min_importance))
                        ]
                    ),
                    limit=1000
                )
                
                if old_memories[0]:  # old_memories[0] contains the points
                    memory_ids = [m.id for m in old_memories[0]]
                    
                    # Delete from Qdrant
                    self.qdrant_client.delete(
                        collection_name="memories",
                        points_selector=models.Filter(
                            must=[models.HasIdCondition(has_id=memory_ids)]
                        )
                    )
                    
                    # Delete from BM25 index
                    if self.bm25_index:
                        self.bm25_index.delete_documents(memory_ids)
                    
                    logger.info(f"🗑️ Cleaned up {len(memory_ids)} old memories")
                    return len(memory_ids)
            
            return 0
        except Exception as e:
            logger.error(f"❌ Error cleaning memories: {e}")
            return 0
    
    def __del__(self):
        """Cleanup"""
        if hasattr(self, 'conn'):
            self.conn.close()


class SQLiteBM25Index:
    """SQLite-based BM25 index for keyword search"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._setup_schema()
    
    def _setup_schema(self):
        """Setup BM25 index schema"""
        cursor = self.conn.cursor()
        
        # FTS virtual table - standalone
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                id UNINDEXED,
                text,
                person_id UNINDEXED,
                channel_id UNINDEXED
            )
        """)
        
        self.conn.commit()
    
    def add_document(self, doc_id: str, text: str, person_id: str, channel_id: str):
        """Add document to BM25 index"""
        cursor = self.conn.cursor()
        
        # Insert into FTS table directly
        # First delete if exists (to handle updates)
        cursor.execute("DELETE FROM documents_fts WHERE id = ?", (doc_id,))
        
        cursor.execute("""
            INSERT INTO documents_fts (id, text, person_id, channel_id)
            VALUES (?, ?, ?, ?)
        """, (doc_id, text, person_id, channel_id))
        
        self.conn.commit()
    
    def search(self, query: str, user_id: str = None, channel_id: str = None, limit: int = 20) -> List[Dict]:
        """Search documents using BM25"""
        cursor = self.conn.cursor()
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        if user_id:
            where_conditions.append("person_id = ?")
            params.append(user_id)
        
        if channel_id:
            where_conditions.append("channel_id = ?")
            params.append(channel_id)
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        # Search using FTS
        cursor.execute(f"""
            SELECT id, text, person_id, channel_id,
                   bm25(documents_fts) as score
            FROM documents_fts
            WHERE documents_fts MATCH ? AND {where_clause}
            ORDER BY score
            LIMIT ?
        """, (query, *params, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'text': row[1],
                'person_id': row[2],
                'channel_id': row[3],
                'score': row[4]
            })
        
        return results
    
    def delete_documents(self, doc_ids: List[str]):
        """Delete documents from index"""
        cursor = self.conn.cursor()
        
        for doc_id in doc_ids:
            cursor.execute("DELETE FROM documents_fts WHERE id = ?", (doc_id,))
        
        self.conn.commit()
    
    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()