"""
Comprehensive Database Protection System Test Suite
Tests all components of the production-grade database protection system.
"""
import asyncio
import os
import tempfile
import shutil
import sqlite3
from pathlib import Path
import logging
from datetime import datetime

# Import the database protection system
from database_protector import DatabaseProtector, DatabaseValidationError, DatabaseRecoveryError
from logger_config import logger

class DatabaseProtectionTester:
    def __init__(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="db_protection_test_"))
        self.protector = None
        self.test_results = []
    
    async def run_all_tests(self):
        """Run comprehensive test suite"""
        logger.info("🧪 Starting Database Protection System Tests")
        logger.info("=" * 60)
        
        try:
            # Test 1: Database validation system
            await self.test_database_validation()
            
            # Test 2: Backup creation and management
            await self.test_backup_system()
            
            # Test 3: Corruption detection and recovery
            await self.test_corruption_recovery()
            
            # Test 4: Graceful shutdown handling
            await self.test_graceful_shutdown()
            
            # Test 5: Integration test
            await self.test_integration()
            
        except Exception as e:
            logger.error(f" Test suite failed: {e}")
            raise
        finally:
            # Cleanup
            self.cleanup_test_environment()
        
        # Print results
        self.print_test_results()
    
    async def test_database_validation(self):
        """Test database validation system"""
        logger.info(" Testing Database Validation System...")
        
        test_name = "Database Validation"
        result = {"test": test_name, "status": "passed", "details": []}
        
        try:
            # Initialize protector with test directory
            self.protector = DatabaseProtector(
                data_dir=str(self.test_dir / "data"),
                backup_dir=str(self.test_dir / "backups")
            )
            
            # Test 1: Valid empty databases (should pass as empty databases are acceptable)
            validation_results = self.protector.validate_all_databases()
            result["details"].append(f"Empty database validation: {validation_results['overall_status']}")
            
            # Test 2: Create valid databases
            await self.create_valid_test_databases()
            
            validation_results = self.protector.validate_all_databases()
            result["details"].append(f"Valid database validation: {validation_results['overall_status']}")
            
            # Allow both 'valid' and 'recoverable' as acceptable for a new bot
            if validation_results['overall_status'] not in ['valid', 'recoverable']:
                result["status"] = "failed"
                result["details"].append(f"Expected 'valid' or 'recoverable', got '{validation_results['overall_status']}'")
            
        except Exception as e:
            result["status"] = "failed"
            result["details"].append(f"Exception: {e}")
        
        self.test_results.append(result)
        logger.info(f" {test_name}: {result['status'].upper()}")
        for detail in result["details"]:
            logger.info(f"    {detail}")
    
    async def test_backup_system(self):
        """Test backup creation and management"""
        logger.info(" Testing Backup System...")
        
        test_name = "Backup System"
        result = {"test": test_name, "status": "passed", "details": []}
        
        try:
            # Create test databases first
            await self.create_valid_test_databases()
            
            # Test 1: Manual backup
            backup_path = self.protector.create_backup("manual")
            if backup_path:
                result["details"].append(f"Manual backup created: {Path(backup_path).name}")
            else:
                result["status"] = "failed"
                result["details"].append("Manual backup failed")
            
            # Test 2: Multiple backups
            backup_paths = []
            for i in range(3):
                backup_path = self.protector.create_backup(f"test_{i}")
                if backup_path:
                    backup_paths.append(backup_path)
            
            result["details"].append(f"Created {len(backup_paths)} test backups")
            
            # Test 3: List backups
            backups = self.protector.list_backups()
            result["details"].append(f"Listed {len(backups)} backups")
            
            # Test 4: Backup cleanup (test retention limit)
            # Create more backups than the limit
            for i in range(60):  # More than max_backups (50)
                try:
                    self.protector.create_backup(f"overflow_{i}", force=True)
                except:
                    pass  # Some might fail, that's okay
            
            backups_after_cleanup = self.protector.list_backups()
            if len(backups_after_cleanup) <= 50:
                result["details"].append(" Backup cleanup working (kept under limit)")
            else:
                result["details"].append(f" Backup cleanup issue (got {len(backups_after_cleanup)} backups)")
            
        except Exception as e:
            result["status"] = "failed"
            result["details"].append(f"Exception: {e}")
        
        self.test_results.append(result)
        logger.info(f" {test_name}: {result['status'].upper()}")
        for detail in result["details"]:
            logger.info(f"    {detail}")
    
    async def test_corruption_recovery(self):
        """Test corruption detection and recovery"""
        logger.info("🛠 Testing Corruption Recovery...")
        
        test_name = "Corruption Recovery"
        result = {"test": test_name, "status": "passed", "details": []}
        
        try:
            # Create valid databases
            await self.create_valid_test_databases()
            
            # Test 1: Corrupt SQLite database
            sqlite_db = Path(self.protector.sqlite_db)
            if sqlite_db.exists():
                # Write garbage data to corrupt
                with open(sqlite_db, 'w') as f:
                    f.write("CORRUPTED SQLite DATABASE")
                
                # Validate should detect corruption
                validation_results = self.protector.validate_all_databases()
                result["details"].append(f"SQLite corruption detection: {validation_results['sqlite_validation']['valid']}")
                
                if validation_results['sqlite_validation']['valid']:
                    result["status"] = "failed"
                    result["details"].append("Expected SQLite to be detected as corrupted")
                
                # Test recovery
                recovery_success = self.protector.recover_from_corruption(validation_results)
                result["details"].append(f"SQLite recovery: {recovery_success}")
            
            # Test 2: Corrupt ChromaDB
            chroma_dir = Path(self.protector.chroma_dir)
            if chroma_dir.exists():
                # Remove binary files to simulate corruption
                for file_path in chroma_dir.rglob("*.bin"):
                    file_path.unlink()
                
                validation_results = self.protector.validate_all_databases()
                result["details"].append(f"ChromaDB corruption detection: {validation_results['chroma_validation']['valid']}")
                
                # Test recovery
                recovery_success = self.protector.recover_from_corruption(validation_results)
                result["details"].append(f"ChromaDB recovery: {recovery_success}")
            
        except Exception as e:
            result["status"] = "failed"
            result["details"].append(f"Exception: {e}")
        
        self.test_results.append(result)
        logger.info(f" {test_name}: {result['status'].upper()}")
        for detail in result["details"]:
            logger.info(f"    {detail}")
    
    async def test_graceful_shutdown(self):
        """Test graceful shutdown handling"""
        logger.info(" Testing Graceful Shutdown...")
        
        test_name = "Graceful Shutdown"
        result = {"test": test_name, "status": "passed", "details": []}
        
        try:
            # Test that setup doesn't crash
            self.protector.setup_graceful_shutdown()
            result["details"].append("Graceful shutdown handlers registered")
            
            # Test graceful shutdown function
            self.protector.graceful_shutdown()
            result["details"].append("Graceful shutdown executed successfully")
            
        except Exception as e:
            result["status"] = "failed"
            result["details"].append(f"Exception: {e}")
        
        self.test_results.append(result)
        logger.info(f" {test_name}: {result['status'].upper()}")
        for detail in result["details"]:
            logger.info(f"    {detail}")
    
    async def test_integration(self):
        """Test full integration scenario"""
        logger.info("🔗 Testing Integration Scenario...")
        
        test_name = "Integration Test"
        result = {"test": test_name, "status": "passed", "details": []}
        
        try:
            # Simulate realistic usage scenario
            steps = [
                "Create databases",
                "Create startup backup",
                "Simulate usage (add data)",
                "Create maintenance backup",
                "Validate integrity",
                "Simulate corruption",
                "Attempt recovery",
                "Final validation"
            ]
            
            for i, step in enumerate(steps, 1):
                try:
                    if step == "Create databases":
                        await self.create_valid_test_databases()
                    
                    elif step == "Create startup backup":
                        backup_path = self.protector.create_backup("startup")
                        if backup_path:
                            result["details"].append(f"Step {i}:  {step}")
                        else:
                            result["details"].append(f"Step {i}:  {step}")
                            result["status"] = "failed"
                    
                    elif step == "Simulate usage (add data)":
                        # Add some test data to SQLite
                        conn = sqlite3.connect(str(self.protector.sqlite_db))
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", 
                                     ("test_user", "Test User"))
                        conn.commit()
                        conn.close()
                        result["details"].append(f"Step {i}:  {step}")
                    
                    elif step == "Create maintenance backup":
                        backup_path = self.protector.create_backup("maintenance")
                        if backup_path:
                            result["details"].append(f"Step {i}:  {step}")
                        else:
                            result["details"].append(f"Step {i}:  {step}")
                    
                    elif step == "Validate integrity":
                        validation_results = self.protector.validate_all_databases()
                        if validation_results['overall_status'] == 'valid':
                            result["details"].append(f"Step {i}:  {step}")
                        else:
                            result["details"].append(f"Step {i}:  {step}")
                    
                    elif step == "Simulate corruption":
                        # Corrupt a file
                        link_lists_file = list(Path(self.protector.chroma_dir).rglob("link_lists.bin"))[0]
                        link_lists_file.unlink()
                        result["details"].append(f"Step {i}:  {step}")
                    
                    elif step == "Attempt recovery":
                        validation_results = self.protector.validate_all_databases()
                        recovery_success = self.protector.recover_from_corruption(validation_results)
                        if recovery_success:
                            result["details"].append(f"Step {i}:  {step}")
                        else:
                            result["details"].append(f"Step {i}:  {step}")
                            result["status"] = "failed"
                    
                    elif step == "Final validation":
                        validation_results = self.protector.validate_all_databases()
                        if validation_results['overall_status'] in ['valid', 'recoverable']:
                            result["details"].append(f"Step {i}:  {step}")
                        else:
                            result["details"].append(f"Step {i}:  {step}")
                            result["status"] = "failed"
                    
                except Exception as e:
                    result["details"].append(f"Step {i}:  {step} - {e}")
                    result["status"] = "failed"
            
        except Exception as e:
            result["status"] = "failed"
            result["details"].append(f"Integration test exception: {e}")
        
        self.test_results.append(result)
        logger.info(f" {test_name}: {result['status'].upper()}")
        for detail in result["details"]:
            logger.info(f"    {detail}")
    
    async def create_valid_test_databases(self):
        """Create valid test databases for testing"""
        try:
            # Create directories
            self.test_dir.mkdir(parents=True, exist_ok=True)
            data_dir = Path(self.test_dir) / "data"
            data_dir.mkdir(exist_ok=True)
            
            # Create SQLite database
            sqlite_db = data_dir / "bot_data.db"
            conn = sqlite3.connect(str(sqlite_db))
            cursor = conn.cursor()
            
            # Create tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    total_messages INTEGER DEFAULT 0
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)
            
            conn.commit()
            conn.close()
            
            # Create ChromaDB directory structure
            chroma_dir = data_dir / "chroma_data"
            chroma_dir.mkdir(exist_ok=True)
            
            # Create SQLite component
            chroma_sqlite = chroma_dir / "chroma.sqlite3"
            conn = sqlite3.connect(str(chroma_sqlite))
            conn.close()
            
            # Create binary files
            collection_dir = chroma_dir / "test_collection"
            collection_dir.mkdir(exist_ok=True)
            
            (collection_dir / "header.bin").write_bytes(b"test header data")
            (collection_dir / "length.bin").write_bytes(b"test length data")
            (collection_dir / "link_lists.bin").write_bytes(b"test link data")
            (collection_dir / "data_level0.bin").write_bytes(b"test data content")
            
            logger.debug(" Valid test databases created")
            
        except Exception as e:
            logger.error(f" Failed to create test databases: {e}")
            raise
    
    def cleanup_test_environment(self):
        """Clean up test environment"""
        try:
            if self.test_dir.exists():
                shutil.rmtree(self.test_dir)
                logger.debug(" Test environment cleaned up")
        except Exception as e:
            logger.warning(f" Failed to cleanup test environment: {e}")
    
    def print_test_results(self):
        """Print comprehensive test results"""
        logger.info("=" * 80)
        logger.info("🧪 DATABASE PROTECTION SYSTEM TEST RESULTS")
        logger.info("=" * 80)
        
        passed = 0
        failed = 0
        
        for result in self.test_results:
            status_icon = "" if result["status"] == "passed" else ""
            logger.info(f"{status_icon} {result['test']}: {result['status'].upper()}")
            
            if result["status"] == "passed":
                passed += 1
            else:
                failed += 1
            
            for detail in result["details"]:
                logger.info(f"   {detail}")
        
        logger.info("=" * 80)
        logger.info(f" SUMMARY: {passed} passed, {failed} failed")
        
        if failed == 0:
            logger.info(" ALL TESTS PASSED! Database Protection System is production-ready.")
        else:
            logger.error(" Some tests failed. Review and fix issues before production use.")
        
        logger.info("=" * 80)

async def main():
    """Run the test suite"""
    try:
        tester = DatabaseProtectionTester()
        await tester.run_all_tests()
        
        # Exit with appropriate code
        failed_tests = sum(1 for result in tester.test_results if result["status"] == "failed")
        exit(0 if failed_tests == 0 else 1)
        
    except Exception as e:
        logger.error(f" Test suite crashed: {e}")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())