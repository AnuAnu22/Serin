"""
Enhanced API Routes - Qdrant Migration Support
Updated endpoints for Qdrant memory system integration
"""
import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from logger_config import logger
from debug_logger import log_api_request

# Import Qdrant memory system
try:
    from qdrant_memory_system import QdrantMemorySystem
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

# Import legacy memory system


app = Flask(__name__)
CORS(app)

# Global memory system instance
memory_system = None

def init_memory_system(data_dir: str = "./bot_data", qdrant_host: str = "localhost", qdrant_port: int = 6333):
    """Initialize memory system based on configuration"""
    global memory_system
    
    if QDRANT_AVAILABLE:
        try:
            memory_system = QdrantMemorySystem(data_dir, qdrant_host, qdrant_port)
            logger.info("✅ Qdrant Memory System initialized")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize Qdrant: {e}")
    
    logger.error("❌ No memory system available")
    return False

@app.route('/')
def index():
    """Main control panel page"""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Get system status"""
    log_api_request(request)
    
    try:
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
        
        return jsonify(status)
    except Exception as e:
        logger.error(f"❌ Error getting status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """Get memory system statistics"""
    log_api_request(request)
    
    try:
        if not memory_system:
            return jsonify({'error': 'Memory system not initialized'}), 500
        
        stats = memory_system.get_stats()
        
        # Add additional Qdrant-specific stats if available
        if hasattr(memory_system, 'qdrant_client'):
            try:
                collection_info = memory_system.qdrant_client.get_collection("memories")
                stats['qdrant_collection'] = {
                    'status': collection_info.status,
                    'vectors_count': collection_info.vectors_count,
                    'config': {
                        'hnsw_m': collection_info.config.params.hnsw_config.m if collection_info.config.params.hnsw_config else None,
                        'hnsw_ef': collection_info.config.params.hnsw_config.ef if collection_info.config.params.hnsw_config else None
                    }
                }
            except Exception as e:
                logger.warning(f"Could not get Qdrant collection info: {e}")
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"❌ Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['POST'])
def search_memories():
    """Search memories using hybrid search (Qdrant) or legacy search (ChromaDB)"""
    log_api_request(request)
    
    try:
        if not memory_system:
            return jsonify({'error': 'Memory system not initialized'}), 500
        
        data = request.get_json()
        query = data.get('query', '')
        user_id = data.get('user_id')
        channel_id = data.get('channel_id')
        n_results = data.get('n_results', 5)
        time_decay_days = data.get('time_decay_days', 60)
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        # Use appropriate search method based on memory system
        if hasattr(memory_system, 'search_hybrid'):
            # Qdrant hybrid search
            filters = {}
            if channel_id:
                filters['channel_id'] = channel_id
            
            results = memory_system.search_hybrid(query, user_id, n_results, **filters)
        else:
            return jsonify({'error': 'Hybrid search not available'}), 501
        
        # Add search metadata
        response = {
            'query': query,
            'user_id': user_id,
            'channel_id': channel_id,
            'n_results': n_results,
            'results_count': len(results),
            'results': results,
            'search_type': 'hybrid' if hasattr(memory_system, 'search_hybrid') else 'legacy'
        }
        
        return jsonify(response)
    except Exception as e:
        logger.error(f"❌ Error searching memories: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/memories', methods=['POST'])
def add_memory():
    """Add a new memory"""
    log_api_request(request)
    
    try:
        if not memory_system:
            return jsonify({'error': 'Memory system not initialized'}), 500
        
        data = request.get_json()
        content = data.get('content', '').strip()
        user_id = data.get('user_id')
        username = data.get('username')
        channel_id = data.get('channel_id')
        participants = data.get('participants', [])
        emotional_tone = data.get('emotional_tone', 'neutral')
        importance = data.get('importance', 0.5)
        source_message_id = data.get('source_message_id')
        
        if not content or not user_id:
            return jsonify({'error': 'Content and user_id are required'}), 400
        
        # Use appropriate add method based on memory system
        if hasattr(memory_system, 'add_memory_enhanced'):
            # Qdrant enhanced memory addition
            memory_id = memory_system.add_memory_enhanced(
                content=content,
                user_id=user_id,
                username=username,
                channel_id=channel_id,
                participants=participants,
                emotional_tone=emotional_tone,
                importance=importance,
                source_message_id=source_message_id
            )
        else:
            return jsonify({'error': 'Enhanced memory addition not available'}), 501
        
        return jsonify({
            'memory_id': memory_id,
            'message': 'Memory added successfully',
            'content_preview': content[:100] + '...' if len(content) > 100 else content
        })
    except Exception as e:
        logger.error(f"❌ Error adding memory: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/memories/<memory_id>', methods=['GET'])
def get_memory(memory_id):
    """Get specific memory by ID"""
    log_api_request(request)
    
    try:
        if not memory_system:
            return jsonify({'error': 'Memory system not initialized'}), 500
        
        # This would need to be implemented in the memory system
        # For now, return error as it's not a standard operation
        return jsonify({'error': 'Get memory by ID not implemented'}), 501
    except Exception as e:
        logger.error(f"❌ Error getting memory: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['GET'])
def get_user_profile(user_id):
    """Get user profile"""
    log_api_request(request)
    
    try:
        if not memory_system:
            return jsonify({'error': 'Memory system not initialized'}), 500
        
        profile = memory_system.get_user_profile(user_id)
        
        if not profile:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify(profile)
    except Exception as e:
        logger.error(f"❌ Error getting user profile: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['PUT'])
def update_user_profile(user_id):
    """Update user profile"""
    log_api_request(request)
    
    try:
        if not memory_system:
            return jsonify({'error': 'Memory system not initialized'}), 500
        
        data = request.get_json()
        username = data.get('username')
        display_name = data.get('display_name')
        
        if not username:
            return jsonify({'error': 'Username is required'}), 400
        
        memory_system.upsert_user(user_id, username, display_name)
        
        return jsonify({'message': 'User profile updated successfully'})
    except Exception as e:
        logger.error(f"❌ Error updating user profile: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/conversation/<channel_id>', methods=['GET'])
def get_conversation(channel_id):
    """Get recent conversation for a channel"""
    log_api_request(request)
    
    try:
        if not memory_system:
            return jsonify({'error': 'Memory system not initialized'}), 500
        
        limit = request.args.get('limit', 20, type=int)
        user_id = request.args.get('user_id')
        
        if hasattr(memory_system, 'get_recent_conversation'):
            # Qdrant method
            conversation = memory_system.get_recent_conversation(
                channel_id=channel_id,
                user_id=user_id,
                limit=limit
            )
        else:
            conversation = []
        
        return jsonify({
            'channel_id': channel_id,
            'limit': limit,
            'messages_count': len(conversation),
            'messages': conversation
        })
    except Exception as e:
        logger.error(f"❌ Error getting conversation: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cleanup', methods=['POST'])
def cleanup_memories():
    """Clean up old memories"""
    log_api_request(request)
    
    try:
        if not memory_system:
            return jsonify({'error': 'Memory system not initialized'}), 500
        
        data = request.get_json()
        days_old = data.get('days_old', 90)
        min_importance = data.get('min_importance', 0.3)
        
        if hasattr(memory_system, 'cleanup_old_memories'):
            cleaned_count = memory_system.cleanup_old_memories(days_old, min_importance)
            return jsonify({
                'message': f'Cleaned up {cleaned_count} old memories',
                'cleaned_count': cleaned_count,
                'criteria': {
                    'days_old': days_old,
                    'min_importance': min_importance
                }
            })
        else:
            return jsonify({'error': 'Cleanup not available for this memory system'}), 501
    except Exception as e:
        logger.error(f"❌ Error cleaning memories: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """Test Qdrant connection"""
    log_api_request(request)
    
    try:
        data = request.get_json()
        qdrant_host = data.get('qdrant_host', 'localhost')
        qdrant_port = data.get('qdrant_port', 6333)
        
        if not QDRANT_AVAILABLE:
            return jsonify({'error': 'Qdrant not available'}), 501
        
        try:
            from qdrant_client import QdrantClient
            test_client = QdrantClient(host=qdrant_host, port=qdrant_port)
            
            # Try to get cluster info
            cluster_info = test_client.get_cluster_info()
            
            return jsonify({
                'success': True,
                'message': 'Qdrant connection successful',
                'cluster_info': {
                    'status': cluster_info.status,
                    'local_storage': cluster_info.local_storage,
                    'peers': cluster_info.peers
                }
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Qdrant connection failed: {str(e)}'
            }), 400
    except Exception as e:
        logger.error(f"❌ Error testing connection: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    log_api_request(request)
    
    try:
        config = {
            'use_qdrant': os.getenv('USE_QDRANT', 'true').lower() == 'true',
            'qdrant_host': os.getenv('QDRANT_HOST', 'localhost'),
            'qdrant_port': os.getenv('QDRANT_PORT', '6333'),
            'data_dir': os.getenv('DATA_DIR', './bot_data'),
            'debug_mode': os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        }
        
        return jsonify(config)
    except Exception as e:
        logger.error(f"❌ Error getting config: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['PUT'])
def update_config():
    """Update configuration"""
    log_api_request(request)
    
    try:
        data = request.get_json()
        
        # Update environment variables (in-memory for this session)
        if 'use_qdrant' in data:
            os.environ['USE_QDRANT'] = str(data['use_qdrant']).lower()
        if 'qdrant_host' in data:
            os.environ['QDRANT_HOST'] = str(data['qdrant_host'])
        if 'qdrant_port' in data:
            os.environ['QDRANT_PORT'] = str(data['qdrant_port'])
        if 'data_dir' in data:
            os.environ['DATA_DIR'] = str(data['data_dir'])
        
        # Reinitialize memory system with new config
        success = init_memory_system(
            data_dir=os.getenv('DATA_DIR', './bot_data'),
            qdrant_host=os.getenv('QDRANT_HOST', 'localhost'),
            qdrant_port=int(os.getenv('QDRANT_PORT', '6333'))
        )
        
        if not success:
            return jsonify({'error': 'Failed to reinitialize memory system'}), 500
        
        return jsonify({
            'message': 'Configuration updated successfully',
            'config': {
                'use_qdrant': os.getenv('USE_QDRANT', 'true').lower() == 'true',
                'qdrant_host': os.getenv('QDRANT_HOST', 'localhost'),
                'qdrant_port': os.getenv('QDRANT_PORT', '6333'),
                'data_dir': os.getenv('DATA_DIR', './bot_data')
            }
        })
    except Exception as e:
        logger.error(f"❌ Error updating config: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    log_api_request(request)
    
    try:
        health = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'memory_system': 'unknown',
            'uptime': 'N/A'
        }
        
        if memory_system:
            if hasattr(memory_system, 'qdrant_client'):
                health['memory_system'] = 'Qdrant'
                health['qdrant_status'] = 'connected' if memory_system.qdrant_client else 'disconnected'
            else:
                health['memory_system'] = 'ChromaDB'
        
        return jsonify(health)
    except Exception as e:
        logger.error(f"❌ Error in health check: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Initialize memory system
    if not init_memory_system():
        logger.error("❌ Failed to initialize memory system. Exiting.")
        exit(1)
    
    # Start Flask app
    port = int(os.getenv('CONTROL_PANEL_PORT', 8080))
    debug = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
    
    logger.info(f"🌐 Starting control panel on port {port}")
    logger.info(f"🧠 Memory system: {memory_system.__class__.__name__ if memory_system else 'None'}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)

def register_enhanced_routes(app_instance, bot_state, broadcast_func):
    """Register enhanced routes on an existing Flask app instance"""
    # This function is a placeholder for now, as the routes are currently defined globally.
    # In a proper refactor, we would move the route definitions inside a blueprint or this function.
    # For now, we'll just log that it was called.
    logger.info("✅ Enhanced routes registered (placeholder)")
    pass
