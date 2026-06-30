"""Memory write methods — chunking, dedup, embedding, upsert.
Extracted from store.py. These are standalone functions that
operate on a QdrantMemorySystem instance passed as first arg.
"""
import hashlib
import uuid
import json
from typing import List, Dict, Optional
from serin.config.logger import logger
from serin.config.debug_logger import log_memory
from serin.state.thinking_filter import filter_for_memory


def generate_memory_id(store, source_message_id: Optional[str], chunk_index: int = 0) -> str:
        """Generate deterministic ID for idempotent ingestion"""
        if source_message_id:
            namespace = uuid.uuid5(uuid.NAMESPACE_DNS, "serin.ai")
            return str(uuid.uuid5(namespace, f"{source_message_id}:{chunk_index}"))
        else:
            return str(uuid.uuid4())
    
def _chunk_content(store, content: str, min_tokens: int = 200, max_tokens: int = 600) -> List[str]:
        """Split content into appropriate chunks."""
        chars_per_token = 4
        max_chars = max_tokens * chars_per_token
        
        sentences = content.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 2 <= max_chars:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
                
                if len(current_chunk) > max_chars:
                    chunks.append(current_chunk[:max_chars])
                    current_chunk = current_chunk[max_chars:]
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        if len(chunks) > 1 and len(chunks[0]) < min_tokens:
            chunks[1] = chunks[0] + " " + chunks[1]
            chunks.pop(0)
        
        return chunks
    
def _build_payload(store, content: str, user_id: str, chunk_index: int, total_chunks: int, **kwargs) -> Dict:
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
            "compressed": kwargs.get('compressed', False),
            "source_message_count": kwargs.get('source_message_count', 0),
            "evidence_class": kwargs.get('evidence_class', 'conversation'),
            "speech_act": kwargs.get('speech_act', 'statement'),
            "is_objective": kwargs.get('is_objective', False),
            "extracted_facts": kwargs.get('extracted_facts', []),
            "topics": kwargs.get('topics', []),
            "summary_extract": kwargs.get('summary_extract', ''),
            "summary_abstract": kwargs.get('summary_abstract', ''),
            "embedding_model": "nomic-embed-text-v1.5",
            "embedding_dim": store.embedding_dim,
            "embedding_version": "v1",
            "parent_id": kwargs.get('parent_id', ''),
            "linked_ids": kwargs.get('linked_ids', []),
            "chunk_index": chunk_index,
            "total_chunks": total_chunks
        }
    
def _is_duplicate(store, content: str, user_id: str, source_message_id: Optional[str] = None) -> bool:
        """Check if memory already exists"""
        if source_message_id:
            cursor = store.conn.cursor()
            cursor.execute("SELECT id FROM background_jobs WHERE memory_id LIKE ? AND job_type = 'dedup'", 
                          (f"%{source_message_id}%",))
            if cursor.fetchone():
                return True
        
        if store.qdrant_client:
            try:
                if source_message_id:
                    results = store.qdrant_client.scroll(
                        collection_name="memories",
                        scroll_filter=models.Filter(
                            must=[models.FieldCondition(key="source_message_id", match=models.MatchValue(value=source_message_id))]
                        ),
                        limit=1
                    )
                    if results[0]:
                        return True

                existing_id = store._get_existing_memory_id(content, user_id)
                if existing_id:
                    return True
                    
            except Exception as e:
                logger.warning(f" Error checking duplicates in Qdrant: {e}")
        
        return False
    
def _get_existing_memory_id(store, content: str, user_id: str) -> Optional[str]:
        """Get existing memory ID for duplicate content"""
        if not store.qdrant_client:
            return None
            
        try:
            should_conditions = [
                models.FieldCondition(key="person_id", match=models.MatchValue(value=user_id)),
                models.FieldCondition(key="text", match=models.MatchValue(value=content))
            ]
            
            results = store.qdrant_client.scroll(
                collection_name="memories",
                scroll_filter=models.Filter(must=should_conditions),
                limit=1,
                with_payload=False
            )
            
            if results[0]:
                return results[0][0].id
                
            return None
            
        except Exception as e:
            logger.error(f" Error checking existing memory ID: {e}")
            return None
    
def _queue_background_jobs(store, memory_ids: List[str], kwargs: Dict):
        """Queue background processing jobs"""
        cursor = store.conn.cursor()
        
        for memory_id in memory_ids:
            cursor.execute("""
                INSERT INTO background_jobs (job_type, memory_id, payload, priority)
                VALUES (?, ?, ?, ?)
            """, ("summarize", memory_id, json.dumps(kwargs), 1))
            
            cursor.execute("""
                INSERT INTO background_jobs (job_type, memory_id, payload, priority)
                VALUES (?, ?, ?, ?)
            """, ("rerank", memory_id, json.dumps(kwargs), 2))
        
        store.conn.commit()
    
def add_memory_enhanced(store, content: str, user_id: str, **kwargs) -> Optional[str]:
        """Enhanced memory ingestion with chunking and idempotency"""
        content = filter_for_memory(content)
        
        try:
            if store._is_duplicate(content, user_id, kwargs.get('source_message_id')):
                existing_id = store._get_existing_memory_id(content, user_id)
                if existing_id:
                    return existing_id
            
            chunks = store._chunk_content(content, min_tokens=200, max_tokens=600)
            
            embeddings = []
            if store.embedding_model:
                try:
                    prefixed_chunks = [c for c in chunks]
                    chunk_embeddings = store.embedding_model.encode(prefixed_chunks)
                    embeddings = [emb.tolist() for emb in chunk_embeddings]
                except Exception as e:
                    logger.error("memory.embedding_failed_skipping_write", extra={
                        "error": str(e),
                        "content_preview": content[:50],
                        "user_id": user_id,
                    }, exc_info=True)
                    return None
            else:
                logger.warning("memory.embedding_model_unavailable", extra={
                    "user_id": user_id,
                    "content_preview": content[:50],
                })
                return None
            
            memory_ids = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                memory_id = store.generate_memory_id(kwargs.get('source_message_id'), i)
                
                payload = store._build_payload(chunk, user_id, i, len(chunks), **kwargs)
                
                if store.qdrant_client:
                    try:
                        store.qdrant_client.upsert(
                            collection_name="memories",
                            points=[models.PointStruct(
                                id=memory_id,
                                vector=embedding,
                                payload=payload
                            )]
                        )
                    except Exception as e:
                        logger.error(f" Error upserting to Qdrant: {e}")
                
                if store.bm25_index:
                    try:
                        store.bm25_index.add_document(memory_id, chunk, user_id, kwargs.get('channel_id'))
                    except Exception as e:
                        logger.error(f" Error adding to BM25: {e}")
                
                memory_ids.append(memory_id)
            
            store._queue_background_jobs(memory_ids, kwargs)
            store._update_ingestion_stats(len(memory_ids))
            
            logger.debug("memory.write_complete", extra={
                "chunks": len(memory_ids),
                "content_preview": content[:50],
                "user_id": user_id,
            })
            log_memory(content, payload)

            return memory_ids[0] if memory_ids else None

        except Exception as e:
            logger.error("memory.write_failed", extra={
                "error": str(e),
                "content_preview": content[:50],
                "user_id": user_id,
            }, exc_info=True)
            return None
    
