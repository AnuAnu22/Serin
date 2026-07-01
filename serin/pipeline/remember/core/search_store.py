"""Hybrid search methods — BM25 + vector + rerank.
Extracted from store.py.
"""
from datetime import datetime
from typing import List, Dict, Optional
from serin.state.logger import logger


def search_hybrid(store, query: str, user_id: Optional[str] = None, n_results: int = 5, **filters) -> List[Dict]:
        """Hybrid search: BM25 + Vector + Rerank"""
        logger.debug("memory.search_start", extra={
            "query_preview": query[:50],
            "user_id": user_id or "all",
            "n_results": n_results,
        })
        try:
            bm25_candidates = []
            if store.bm25_index:
                try:
                    bm25_candidates = store.bm25_index.search(
                        query=query,
                        user_id=user_id,
                        channel_id=filters.get('channel_id'),
                        limit=20
                    )
                except Exception as e:
                    logger.error("memory.bm25_search_failed", extra={
                        "error": str(e),
                        "query_preview": query[:50],
                    })

            vector_candidates = []
            if store.qdrant_client and store.embedding_model:
                try:
                    qdrant_filter = store._build_qdrant_filter(user_id, filters)
                    query_embedding = store.embedding_model.encode([f"search_query: {query}"])[0].tolist()
                    results = store.qdrant_client.query_points(
                        collection_name="memories",
                        query=query_embedding,
                        query_filter=qdrant_filter,
                        limit=50,
                        with_payload=True
                    ).points
                    vector_candidates = [{'id': r.id, 'score': r.score, 'payload': r.payload} for r in results]
                except Exception as e:
                    logger.error("memory.vector_search_failed", extra={
                        "error": str(e),
                        "query_preview": query[:50],
                    })

            merged_candidates = store._merge_candidates(bm25_candidates, vector_candidates)
            reranked_results = store._rerank_results_simple(query, merged_candidates, n_results)
            results = store._condense_results(reranked_results)
            logger.debug("memory.search_complete", extra={
                "query_preview": query[:50],
                "results_count": len(results),
            })
            return results

        except Exception as e:
            logger.error("memory.search_failed", extra={
                "error": str(e),
                "query_preview": query[:50],
            }, exc_info=True)
            return []
    
def _build_qdrant_filter(store, user_id: Optional[str], filters: Dict) -> models.Filter:
        """Build Qdrant payload filter"""
        conditions = []
        
        if user_id:
            conditions.append(models.FieldCondition(key="person_id", match=models.MatchValue(value=user_id)))
        
        if filters.get('channel_id'):
            conditions.append(models.FieldCondition(key="channel_id", match=models.MatchValue(value=filters['channel_id'])))
        
        if filters.get('start_time'):
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
        
        if filters.get('min_importance'):
            conditions.append(models.FieldCondition(key="importance", range=models.Range(gte=filters['min_importance'])))
        
        if filters.get('memory_type'):
            conditions.append(models.FieldCondition(key="memory_type", match=models.MatchValue(value=filters['memory_type'])))
        
        return models.Filter(must=conditions) if conditions else None
    
def _merge_candidates(store, bm25_candidates: List[Dict], vector_candidates: List[Dict]) -> List[Dict]:
        """Merge results from BM25 and vector search"""
        merged = {}
        
        for candidate in bm25_candidates:
            candidate_id = candidate.get('id')
            if candidate_id:
                merged[candidate_id] = {
                    'id': candidate_id,
                    'bm25_score': candidate.get('score', 0),
                    'vector_score': 0,
                    'payload': {
                        'text': candidate.get('text', ''),
                        'person_id': candidate.get('person_id', ''),
                        'person_display': candidate.get('person_id', ''),
                        'channel_id': candidate.get('channel_id', ''),
                        'timestamp': '',
                        'importance': 0.5,
                        'memory_type': 'utterance',
                    }
                }
        
        for candidate in vector_candidates:
            candidate_id = candidate.get('id')
            if candidate_id:
                if candidate_id in merged:
                    merged[candidate_id]['vector_score'] = candidate.get('score', 0)
                    if candidate.get('payload'):
                        merged[candidate_id]['payload'] = candidate.get('payload')
                else:
                    merged[candidate_id] = {
                        'id': candidate_id,
                        'bm25_score': 0,
                        'vector_score': candidate.get('score', 0),
                        'payload': candidate.get('payload', {})
                    }
        
        result_list = list(merged.values())
        for item in result_list:
            bm25 = item.get('bm25_score', 0)
            bm25_contribution = 1.0 / (1.0 + bm25) if bm25 != 0 else 0
            item['combined_score'] = (item['vector_score'] * 0.6) + (bm25_contribution * 0.4)
        
        return result_list
    
def _rerank_results_simple(store, query: str, candidates: List[Dict], top_k: int = 30) -> List[Dict]:
        """Simple reranking based on recency and importance"""
        if len(candidates) <= top_k:
            return candidates

        candidates.sort(key=lambda x: x['combined_score'], reverse=True)
        top_candidates = candidates[:top_k]

        try:
            import serin_core
            scores = [c.get('combined_score', 0) for c in top_candidates]
            age_days_list = []
            for c in top_candidates:
                payload = c.get('payload', {})
                timestamp = payload.get('timestamp', '')
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    age_days_list.append(float((datetime.now() - dt).days))
                except Exception:
                    age_days_list.append(0.0)
            ranked = serin_core.rerank_candidates(scores, age_days_list)
            return [top_candidates[i] for i, _ in ranked]
        except ImportError:
            for candidate in top_candidates:
                payload = candidate.get('payload', {})
                timestamp = payload.get('timestamp')
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        age_days = (datetime.now() - dt).days
                        recency_boost = max(0, 1 - (age_days / 365))
                        candidate['rerank_score'] = candidate['combined_score'] + (recency_boost * 0.2)
                    except Exception:
                        candidate['rerank_score'] = candidate['combined_score']
                else:
                    candidate['rerank_score'] = candidate['combined_score']
                importance = payload.get('importance', 0.5)
                candidate['rerank_score'] += (importance - 0.5) * 0.1
            top_candidates.sort(key=lambda x: x['rerank_score'], reverse=True)
            return top_candidates
    
def _condense_results(store, results: List[Dict]) -> List[Dict]:
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
                'age_days': store._calculate_age_days(payload.get('timestamp', '')),
                'channel_id': payload.get('channel_id', ''),
                'participants': payload.get('participants', []),
                'memory_type': payload.get('memory_type', 'utterance'),
                'importance': payload.get('importance', 0.5)
            })
        
        return condensed
    
def _calculate_age_days(store, timestamp: str) -> int:
        """Calculate age in days from timestamp"""
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return (datetime.now() - dt).days
        except:
            return 0
    
def _update_ingestion_stats(store, count: int):
        """Update ingestion statistics"""
        today = datetime.now().date().isoformat()
        
        cursor = store.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO memory_stats 
            (date, total_memories, ingestion_count)
            VALUES (?, COALESCE((SELECT total_memories FROM memory_stats WHERE date = ?), 0) + ?, ?)
        """, (today, today, count, count))
        store.conn.commit()
    
    # ========================================================================
    # Legacy compatibility methods
    # ========================================================================
    
