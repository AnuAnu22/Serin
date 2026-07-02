"""
Enhanced API Routes - Qdrant Migration Support
Updated endpoints for Qdrant memory system integration
Converted to FastAPI for integration with web_server.py
"""
import importlib.util
from datetime import datetime
from typing import Any, cast

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from serin.d1_3_state_core.logger import logger

QDRANT_AVAILABLE = importlib.util.find_spec("qdrant_client") is not None

# Pydantic models for requests
class SearchRequest(BaseModel):
    query: str
    user_id: str | None = None
    channel_id: str | None = None
    n_results: int = 5
    time_decay_days: int = 60

class MemoryRequest(BaseModel):
    content: str
    user_id: str
    username: str | None = None
    channel_id: str | None = None
    participants: list[str] = []
    emotional_tone: str = 'neutral'
    importance: float = 0.5
    source_message_id: str | None = None

class CleanupRequest(BaseModel):
    days_old: int = 90
    min_importance: float = 0.3

class ConnectionTestRequest(BaseModel):
    qdrant_host: str = 'localhost'
    qdrant_port: int = 6333

class ConfigUpdateRequest(BaseModel):
    use_qdrant: bool | None = None
    qdrant_host: str | None = None
    qdrant_port: int | None = None
    data_dir: str | None = None

def register_enhanced_routes(app: FastAPI, bot_state: dict[str, Any], broadcast_func: Any) -> None:
    """Register enhanced routes on the FastAPI app instance"""

    logger.info(" Registering enhanced API routes...")

    def get_memory_system() -> Any:
        system = bot_state.get('memory_system')
        if not system:
            raise HTTPException(status_code=500, detail="Memory system not initialized")
        return system

    @app.get('/api/enhanced/status')
    async def get_enhanced_status() -> dict[str, Any]:
        """Get system status"""
        try:
            memory_system = bot_state.get('memory_system')
            status = {
                'timestamp': datetime.now().isoformat(),
                'memory_system': 'unknown',
                'qdrant_available': QDRANT_AVAILABLE,
                'memory_system_initialized': memory_system is not None
            }

            if memory_system:
                if hasattr(memory_system, 'qdrant_client'):
                    status['memory_system'] = 'Qdrant'
                    status['qdrant_connected'] = memory_system.qdrant_client is not None
                    status['embedding_available'] = memory_system.embedding_model is not None
                    status['bm25_available'] = memory_system.bm25_index is not None

            return status
        except Exception as e:
            logger.error(f" Error getting status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post('/api/enhanced/search')
    async def search_memories_enhanced(request: SearchRequest) -> dict[str, Any]:
        """Search memories using hybrid search (Qdrant)"""
        try:
            memory_system = get_memory_system()

            # Use appropriate search method based on memory system
            if hasattr(memory_system, 'search_hybrid'):
                # Qdrant hybrid search
                filters = {}
                if request.channel_id:
                    filters['channel_id'] = request.channel_id

                results = memory_system.search_hybrid(
                    request.query,
                    request.user_id,
                    request.n_results,
                    **filters
                )
            else:
                # Fallback or error
                raise HTTPException(status_code=501, detail="Hybrid search not available")

            return {
                'query': request.query,
                'user_id': request.user_id,
                'channel_id': request.channel_id,
                'n_results': request.n_results,
                'results_count': len(results),
                'results': results,
                'search_type': 'hybrid'
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f" Error searching memories: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post('/api/enhanced/memories')
    async def add_memory_enhanced(request: MemoryRequest) -> dict[str, Any]:
        """Add a new memory"""
        try:
            memory_system = get_memory_system()

            if hasattr(memory_system, 'add_memory_enhanced'):
                memory_id = memory_system.add_memory_enhanced(
                    content=request.content,
                    user_id=request.user_id,
                    username=request.username,
                    channel_id=request.channel_id,
                    participants=request.participants,
                    emotional_tone=request.emotional_tone,
                    importance=request.importance,
                    source_message_id=request.source_message_id
                )
            else:
                raise HTTPException(status_code=501, detail="Enhanced memory addition not available")

            return {
                'memory_id': memory_id,
                'message': 'Memory added successfully',
                'content_preview': request.content[:100] + '...' if len(request.content) > 100 else request.content
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f" Error adding memory: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get('/api/enhanced/users/{user_id}')
    async def get_user_profile_enhanced(user_id: str) -> dict[str, Any]:
        """Get user profile"""
        try:
            memory_system = get_memory_system()
            profile = memory_system.get_user_profile(user_id)

            if not profile:
                raise HTTPException(status_code=404, detail="User not found")

            return cast(dict[str, Any], profile)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f" Error getting user profile: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post('/api/enhanced/cleanup')
    async def cleanup_memories_enhanced(request: CleanupRequest) -> dict[str, Any]:
        """Clean up old memories"""
        try:
            memory_system = get_memory_system()

            if hasattr(memory_system, 'cleanup_old_memories'):
                cleaned_count = memory_system.cleanup_old_memories(request.days_old, request.min_importance)
                return {
                    'message': f'Cleaned up {cleaned_count} old memories',
                    'cleaned_count': cleaned_count,
                    'criteria': {
                        'days_old': request.days_old,
                        'min_importance': request.min_importance
                    }
                }
            else:
                raise HTTPException(status_code=501, detail="Cleanup not available")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f" Error cleaning memories: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post('/api/enhanced/test-connection')
    async def test_connection_enhanced(request: ConnectionTestRequest) -> dict[str, Any]:
        """Test Qdrant connection"""
        try:
            if not QDRANT_AVAILABLE:
                raise HTTPException(status_code=501, detail="Qdrant not available")

            try:
                from qdrant_client import QdrantClient
                test_client: Any = QdrantClient(host=request.qdrant_host, port=request.qdrant_port)
                cluster_info = test_client.get_cluster_info()

                return {
                    'success': True,
                    'message': 'Qdrant connection successful',
                    'cluster_info': {
                        'status': cluster_info.status,
                        'local_storage': cluster_info.local_storage,
                        'peers': cluster_info.peers
                    }
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Qdrant connection failed: {str(e)}'
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f" Error testing connection: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    logger.info(" Enhanced routes registered successfully")
