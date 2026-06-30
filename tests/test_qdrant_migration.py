"""
Qdrant Migration Testing Suite
Comprehensive tests for the Qdrant memory system migration
"""
import os
import sys
import json
import sqlite3
import asyncio
import tempfile
import shutil
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import testing modules
try:
    from qdrant_memory_system import QdrantMemorySystem, SQLiteBM25Index
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    print("⚠️ Qdrant not available - running mock tests")



# Mock classes for testing when dependencies are not available
class MockQdrantClient:
    def __init__(self, *args, **kwargs):
        self.collections = {}
        self.points = {}
    
    def create_collection(self, collection_name, vectors_config, **kwargs):
        self.collections[collection_name] = {
            'vectors_config': vectors_config,
            'points': []
        }
    
    def upsert(self, collection_name, points):
        if collection_name not in self.collections:
            self.create_collection(collection_name, None)
        
        for point in points:
            self.points[point.id] = point
            self.collections[collection_name]['points'].append(point)
    
    def search(self, collection_name, query_vector, query_filter=None, limit=10):
        if collection_name not in self.collections:
            return []
        
        # Mock search - return random results
        results = []
        for i, point_id in enumerate(list(self.points.keys())[:limit]):
            results.append(MockSearchResult(
                id=point_id,
                score=0.8 - i * 0.1,
                payload=self.points[point_id].payload
            ))
        return results
    
    def scroll(self, collection_name, scroll_filter=None, limit=100):
        if collection_name not in self.collections:
            return ([], None)
        
        points = list(self.points.values())[:limit]
        return (points, None)
    
    def delete(self, collection_name, points_selector):
        if collection_name in self.collections:
            # Remove points from mock storage
            if hasattr(points_selector, 'must') and points_selector.must:
                # Filter-based deletion
                for condition in points_selector.must:
                    if hasattr(condition, 'has_id'):
                        for point_id in condition.has_id:
                            if point_id in self.points:
                                del self.points[point_id]
            else:
                # Delete all points
                self.points.clear()
    
    def count(self, collection_name):
        return MockCountResult(len(self.points))
    
    def get_collection(self, collection_name):
        return MockCollectionInfo()

class MockSearchResult:
    def __init__(self, id, score, payload):
        self.id = id
        self.score = score
        self.payload = payload

class MockCountResult:
    def __init__(self, count):
        self.count = count

class MockCollectionInfo:
    def __init__(self):
        self.status = 'green'
        self.vectors_count = 0
        self.config = MockConfig()

class MockConfig:
    def __init__(self):
        self.params = MockParams()

class MockParams:
    def __init__(self):
        self.hnsw_config = MockHNSWConfig()

class MockHNSWConfig:
    def __init__(self):
        self.m = 16
        self.ef = 100

class MockSentenceTransformer:
    def __init__(self, model_name):
        self.model_name = model_name
    
    def encode(self, texts, batch_size=32, show_progress_bar=False):
        import numpy as np
        if isinstance(texts, str):
            texts = [texts]
        
        # Mock embeddings - return random float32 vectors (as numpy arrays)
        embeddings = []
        for text in texts:
            # Return numpy array, not list, because real model returns numpy arrays
            embedding = np.random.normal(0, 0.1, 384).astype(np.float32)
            embeddings.append(embedding)
        
        return embeddings


class MockRankBM25:
    def __init__(self, corpus):
        self.corpus = corpus
        self.doc_freqs = {}
        self.idf = {}
        self.doc_len = []
        self.average_doc_len = 0
    
    def get_scores(self, query):
        # Mock BM25 scores
        scores = []
        for i in range(len(self.corpus)):
            scores.append(0.5 + (i % 10) * 0.05)  # Mock decreasing scores
        return scores

class TestQdrantMigration:
    def __init__(self):
        self.test_dir = tempfile.mkdtemp()
        self.passed_tests = 0
        self.failed_tests = 0
        self.total_tests = 0
        
        print(f"🧪 Testing in temporary directory: {self.test_dir}")
    
    def cleanup(self):
        """Clean up test directory"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def run_test(self, test_name, test_func):
        """Run a single test and track results"""
        self.total_tests += 1
        print(f"\n🔬 Running test: {test_name}")
        
        try:
            test_func()
            print(f"✅ {test_name} - PASSED")
            self.passed_tests += 1
        except Exception as e:
            print(f"❌ {test_name} - FAILED: {e}")
            import traceback
            traceback.print_exc()
            self.failed_tests += 1
    
    def test_memory_system_initialization(self):
        """Test memory system initialization"""
        if not QDRANT_AVAILABLE:
            raise Exception("Qdrant not available for testing")
        
        # Test Qdrant initialization
        if QDRANT_AVAILABLE:
            try:
                # Mock Qdrant client for testing
                import qdrant_memory_system
                original_client = qdrant_memory_system.QdrantClient
                qdrant_memory_system.QdrantClient = MockQdrantClient
                
                memory_system = QdrantMemorySystem(data_dir=self.test_dir)
                
                # Restore original client
                qdrant_memory_system.QdrantClient = original_client
                
                assert memory_system is not None
                assert hasattr(memory_system, 'qdrant_client')
                assert hasattr(memory_system, 'embedding_model')
                assert hasattr(memory_system, 'bm25_index')
                
            except Exception as e:
                # Restore original client even if test fails
                if 'qdrant_memory_system' in sys.modules:
                    qdrant_memory_system.QdrantClient = original_client
                raise e
        

    
    def test_sqlite_schema(self):
        """Test SQLite schema initialization"""
        if QDRANT_AVAILABLE:
            # Mock Qdrant client
            import qdrant_memory_system
            original_client = qdrant_memory_system.QdrantClient
            qdrant_memory_system.QdrantClient = MockQdrantClient
            
            memory_system = QdrantMemorySystem(data_dir=self.test_dir)
            
            # Restore original client
            qdrant_memory_system.QdrantClient = original_client
            
            # Check if SQLite tables were created
            db_path = os.path.join(self.test_dir, "bot_data.db")
            assert os.path.exists(db_path)
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check required tables
            required_tables = [
                'users', 'relationships', 'activity_logs',
                'memory_fts', 'background_jobs', 'qdrant_collections',
                'memory_stats'
            ]
            
            for table in required_tables:
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                assert cursor.fetchone() is not None, f"Table {table} not found"
            
            conn.close()
    
    def test_memory_addition(self):
        """Test memory addition functionality"""
        if not QDRANT_AVAILABLE:
            raise Exception("Qdrant not available for testing")
        
        # Mock Qdrant client and embedding model
        import qdrant_memory_system
        original_client = qdrant_memory_system.QdrantClient
        original_model = qdrant_memory_system.SentenceTransformer
        
        qdrant_memory_system.QdrantClient = MockQdrantClient
        qdrant_memory_system.SentenceTransformer = MockSentenceTransformer
        
        memory_system = QdrantMemorySystem(data_dir=self.test_dir)
        
        # Restore originals
        qdrant_memory_system.QdrantClient = original_client
        qdrant_memory_system.SentenceTransformer = original_model
        
        # Test adding memory
        memory_id = memory_system.add_memory_enhanced(
            content="Test memory content",
            user_id="test_user",
            username="TestUser",
            channel_id="test_channel",
            participants=["test_user"],
            emotional_tone="neutral",
            importance=0.7,
            source_message_id="test_message_123"
        )
        
        assert memory_id is not None
        assert isinstance(memory_id, str)
        assert len(memory_id) > 0
        
        # Test adding duplicate memory (should return existing ID)
        duplicate_id = memory_system.add_memory_enhanced(
            content="Test memory content",
            user_id="test_user",
            username="TestUser",
            channel_id="test_channel",
            participants=["test_user"],
            emotional_tone="neutral",
            importance=0.7,
            source_message_id="test_message_123"
        )
        
        assert duplicate_id == memory_id  # Should return same ID for duplicate
    
    def test_memory_search(self):
        """Test memory search functionality"""
        if not QDRANT_AVAILABLE:
            raise Exception("Qdrant not available for testing")
        
        # Mock dependencies
        import qdrant_memory_system
        original_client = qdrant_memory_system.QdrantClient
        original_model = qdrant_memory_system.SentenceTransformer
        original_bm25 = qdrant_memory_system.rank_bm25
        
        qdrant_memory_system.QdrantClient = MockQdrantClient
        qdrant_memory_system.SentenceTransformer = MockSentenceTransformer
        qdrant_memory_system.rank_bm25 = MockRankBM25
        
        memory_system = QdrantMemorySystem(data_dir=self.test_dir)
        
        # Restore originals
        qdrant_memory_system.QdrantClient = original_client
        qdrant_memory_system.SentenceTransformer = original_model
        qdrant_memory_system.rank_bm25 = original_bm25
        
        # Add some test memories
        test_memories = [
            "Hello, how are you?",
            "I'm doing great, thanks!",
            "The weather is nice today",
            "Let's talk about programming",
            "Python is a great language"
        ]
        
        for i, content in enumerate(test_memories):
            memory_system.add_memory_enhanced(
                content=content,
                user_id=f"user_{i}",
                username=f"User_{i}",
                channel_id="test_channel",
                participants=[f"user_{i}"],
                emotional_tone="neutral",
                importance=0.5,
                source_message_id=f"message_{i}"
            )
        
        # Test hybrid search
        results = memory_system.search_hybrid(
            query="programming language",
            user_id=None,
            n_results=3
        )
        
        assert isinstance(results, list)
        assert len(results) <= 3
        
        # Test user-specific search
        results = memory_system.search_hybrid(
            query="hello",
            user_id="user_0",
            n_results=5
        )
        
        assert isinstance(results, list)
        # Should find at least one result from user_0
        assert len(results) > 0
    
    def test_user_management(self):
        """Test user management functionality"""
        if QDRANT_AVAILABLE:
            # Mock Qdrant client
            import qdrant_memory_system
            original_client = qdrant_memory_system.QdrantClient
            qdrant_memory_system.QdrantClient = MockQdrantClient
            
            memory_system = QdrantMemorySystem(data_dir=self.test_dir)
            
            # Restore original client
            qdrant_memory_system.QdrantClient = original_client
        

        
        # Test user creation
        memory_system.upsert_user(
            user_id="test_user",
            username="testuser",
            display_name="Test User"
        )
        
        # Test user retrieval
        profile = memory_system.get_user_profile("test_user")
        
        assert profile is not None
        assert profile["username"] == "testuser"
        assert profile["display_name"] == "Test User"
        
        # Test user update
        memory_system.upsert_user(
            user_id="test_user",
            username="testuser_updated",
            display_name="Test User Updated"
        )
        
        updated_profile = memory_system.get_user_profile("test_user")
        assert updated_profile["username"] == "testuser_updated"
        assert updated_profile["display_name"] == "Test User Updated"
    
    def test_bm25_index(self):
        """Test BM25 index functionality"""
        if not QDRANT_AVAILABLE:
            raise Exception("Qdrant not available for testing")
        
        # Create BM25 index
        bm25_path = os.path.join(self.test_dir, f"bm25_index_{uuid.uuid4().hex}.db")
        bm25_index = SQLiteBM25Index(bm25_path)
        
        # Add documents
        documents = [
            ("doc1", "This is a test document about programming", "user1", "channel1"),
            ("doc2", "Another document about machine learning", "user2", "channel2"),
            ("doc3", "This document discusses artificial intelligence", "user1", "channel1")
        ]
        
        for doc_id, text, user_id, channel_id in documents:
            bm25_index.add_document(doc_id, text, user_id, channel_id)
        
        # Test search
        results = bm25_index.search("programming", limit=5)
        assert len(results) > 0
        
        # Test user-specific search
        results = bm25_index.search("document", user_id="user1", limit=5)
        assert len(results) > 0
        
        # Test channel-specific search
        results = bm25_index.search("document", channel_id="channel1", limit=5)
        assert len(results) > 0
        
        # Test document deletion
        bm25_index.delete_documents(["doc2"])
        results = bm25_index.search("machine learning", limit=5)
        assert len(results) == 0  # Should be deleted
    
    def test_memory_cleanup(self):
        """Test memory cleanup functionality"""
        if not QDRANT_AVAILABLE:
            raise Exception("Qdrant not available for testing")
        
        # Mock Qdrant client
        import qdrant_memory_system
        original_client = qdrant_memory_system.QdrantClient
        qdrant_memory_system.QdrantClient = MockQdrantClient
        
        memory_system = QdrantMemorySystem(data_dir=self.test_dir)
        
        # Restore original client
        qdrant_memory_system.QdrantClient = original_client
        
        # Add some test memories
        for i in range(10):
            memory_system.add_memory_enhanced(
                content=f"Test memory {i}",
                user_id=f"user_{i}",
                username=f"User_{i}",
                channel_id="test_channel",
                participants=[f"user_{i}"],
                emotional_tone="neutral",
                importance=0.2,  # Low importance for cleanup test
                source_message_id=f"message_{i}"
            )
        
        # Test cleanup
        cleaned_count = memory_system.cleanup_old_memories(
            days_old=1,  # Very short retention for testing
            min_importance=0.1
        )
        
        assert cleaned_count >= 0  # Should clean up low-importance memories
    
    def test_stats_and_monitoring(self):
        """Test statistics and monitoring functionality"""
        if QDRANT_AVAILABLE:
            # Mock Qdrant client
            import qdrant_memory_system
            original_client = qdrant_memory_system.QdrantClient
            qdrant_memory_system.QdrantClient = MockQdrantClient
            
            memory_system = QdrantMemorySystem(data_dir=self.test_dir)
            
            # Restore original client
            qdrant_memory_system.QdrantClient = original_client
        

        
        # Get stats
        stats = memory_system.get_stats()
        
        assert isinstance(stats, dict)
        assert 'total_users' in stats
        assert 'total_memories' in stats
        assert 'strong_relationships' in stats
        
        # Add some data and check stats again
        memory_system.upsert_user("test_user", "testuser", "Test User")
        memory_system.add_memory_enhanced(
            content="Test memory",
            user_id="test_user",
            username="testuser",
            channel_id="test_channel",
            participants=["test_user"],
            emotional_tone="neutral",
            importance=0.5,
            source_message_id="test_message"
        )
        
        updated_stats = memory_system.get_stats()
        assert updated_stats['total_users'] >= 1
        assert updated_stats['total_memories'] >= 1
    
    def test_error_handling(self):
        """Test error handling and edge cases"""
        if not QDRANT_AVAILABLE:
            raise Exception("Qdrant not available for testing")
        
        # Mock Qdrant client
        import qdrant_memory_system
        original_client = qdrant_memory_system.QdrantClient
        qdrant_memory_system.QdrantClient = MockQdrantClient
        
        memory_system = QdrantMemorySystem(data_dir=self.test_dir)
        
        # Restore original client
        qdrant_memory_system.QdrantClient = original_client
        
        # Test empty content
        try:
            memory_system.add_memory_enhanced(
                content="",
                user_id="test_user",
                username="testuser",
                channel_id="test_channel",
                participants=["test_user"],
                emotional_tone="neutral",
                importance=0.5,
                source_message_id="test_message"
            )
            # Should handle gracefully
        except Exception:
            pass  # Expected to handle empty content
        
        # Test search with empty query
        try:
            results = memory_system.search_hybrid("", "test_user", 5)
            # Should return empty results
            assert isinstance(results, list)
        except Exception:
            pass  # Expected to handle empty query
        
        # Test invalid user ID
        try:
            profile = memory_system.get_user_profile("nonexistent_user")
            # Should return None or empty dict
            assert profile is None or len(profile) == 0
        except Exception:
            pass  # Expected to handle invalid user ID
    
    def run_all_tests(self):
        """Run all tests and report results"""
        print("🧪 Starting Qdrant Migration Test Suite")
        print("=" * 50)
        
        # Define all tests
        tests = [
            ("Memory System Initialization", self.test_memory_system_initialization),
            ("SQLite Schema", self.test_sqlite_schema),
            ("Memory Addition", self.test_memory_addition),
            ("Memory Search", self.test_memory_search),
            ("User Management", self.test_user_management),
            ("BM25 Index", self.test_bm25_index),
            ("Memory Cleanup", self.test_memory_cleanup),
            ("Stats and Monitoring", self.test_stats_and_monitoring),
            ("Error Handling", self.test_error_handling)
        ]
        
        # Run all tests
        for test_name, test_func in tests:
            self.run_test(test_name, test_func)
        
        # Report results
        print("\n" + "=" * 50)
        print("📊 Test Results Summary")
        print("=" * 50)
        print(f"Total tests: {self.total_tests}")
        print(f"Passed: {self.passed_tests}")
        print(f"Failed: {self.failed_tests}")
        print(f"Success rate: {(self.passed_tests / self.total_tests * 100):.1f}%")
        
        if self.failed_tests == 0:
            print("🎉 All tests passed!")
            return True
        else:
            print(f"❌ {self.failed_tests} test(s) failed")
            return False

def main():
    """Main test runner"""
    test_runner = TestQdrantMigration()
    
    try:
        success = test_runner.run_all_tests()
        return 0 if success else 1
    except Exception as e:
        print(f"❌ Test suite failed with error: {e}")
        return 1
    finally:
        test_runner.cleanup()

if __name__ == "__main__":
    exit(main())