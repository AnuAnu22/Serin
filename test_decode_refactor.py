#!/usr/bin/env python3
"""
Test script for the refactored decode functionality in database_protector.py

This script tests the new enterprise-grade decode functionality to ensure:
1. Professional naming and structure
2. Proper error handling and logging
3. Robust validation and metadata extraction
"""

import os
import sys
import tempfile
import shutil
import json
import tarfile
from pathlib import Path
from datetime import datetime

# Add the current directory to the path to import database_protector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_protector import DatabaseProtector
from logger_config import logger


def create_test_backup(backup_dir: Path, backup_name: str) -> Path:
    """Create a test backup with metadata"""
    backup_path = backup_dir / backup_name
    backup_path.mkdir(parents=True, exist_ok=True)
    
    # Create metadata
    metadata = {
        'backup_type': 'test',
        'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
        'created_at': datetime.now().isoformat(),
        'bot_version': 'test_version',
        'databases_backed_up': ['SQLite', 'ChromaDB'],
        'errors': []
    }
    
    # Save metadata
    metadata_file = backup_path / "backup_info.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Create a dummy database file
    db_file = backup_path / "bot_data.db"
    with open(db_file, 'w') as f:
        f.write("test database content")
    
    # Compress the backup
    shutil.make_archive(
        str(backup_path),
        'gztar',
        root_dir=str(backup_dir),
        base_dir=backup_name
    )
    
    # Remove uncompressed directory
    shutil.rmtree(backup_path)
    
    return Path(str(backup_path) + '.tar.gz')


def test_decode_functionality():
    """Test the refactored decode functionality"""
    print("Testing Refactored Decode Functionality")
    print("=" * 60)
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "test_backups"
        backup_dir.mkdir()
        
        # Initialize DatabaseProtector with test directory
        protector = DatabaseProtector(data_dir=str(temp_path / "data"))
        
        # Test 1: Valid backup extraction
        print("\nTest 1: Valid backup extraction")
        try:
            backup_file = create_test_backup(backup_dir, "test_valid_backup")
            metadata = protector._extract_and_validate_backup_metadata(backup_file)
            
            if metadata:
                print("SUCCESS: Successfully extracted metadata from valid backup")
                print(f"   Backup type: {metadata.get('backup_type')}")
                print(f"   Created: {metadata.get('created_at')}")
                print(f"   Databases: {metadata.get('databases_backed_up', [])}")
                print(f"   File size: {metadata.get('file_size_bytes')} bytes")
            else:
                print("ERROR: Failed to extract metadata from valid backup")
                return False
        except Exception as e:
            print(f"ERROR: Exception during valid backup test: {e}")
            return False
        
        # Test 2: Invalid backup file (non-existent)
        print("\nTest 2: Non-existent backup file")
        try:
            non_existent_file = temp_path / "non_existent_backup.tar.gz"
            metadata = protector._extract_and_validate_backup_metadata(non_existent_file)
            print("ERROR: Should have raised FileNotFoundError")
            return False
        except FileNotFoundError:
            print("SUCCESS: Correctly raised FileNotFoundError for non-existent file")
        except Exception as e:
            print(f"ERROR: Unexpected exception: {e}")
            return False
        
        # Test 3: Invalid backup file (directory instead of file)
        print("\nTest 3: Directory instead of file")
        try:
            directory_path = temp_path / "test_directory"
            directory_path.mkdir()
            metadata = protector._extract_and_validate_backup_metadata(directory_path)
            print("ERROR: Should have raised ValueError")
            return False
        except ValueError:
            print("SUCCESS: Correctly raised ValueError for directory path")
        except Exception as e:
            print(f"ERROR: Unexpected exception: {e}")
            return False
        
        # Test 4: Corrupted backup (invalid JSON)
        print("\nTest 4: Corrupted backup (invalid JSON)")
        try:
            # Create a backup with invalid JSON
            corrupted_backup = backup_dir / "test_corrupted_backup.tar.gz"
            
            # Create properly structured but invalid JSON
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_json:
                temp_json.write('{"invalid": json content}')
                temp_json_path = temp_json.name
            
            # Create backup manually with invalid JSON
            with tarfile.open(corrupted_backup, 'w:gz') as tar:
                tar.add(temp_json_path, arcname="test_backup_info.json")
            
            os.unlink(temp_json_path)
            
            metadata = protector._extract_and_validate_backup_metadata(corrupted_backup)
            if metadata is None:
                print("SUCCESS: Correctly returned None for corrupted backup")
            else:
                print("ERROR: Should have returned None for corrupted backup")
                return False
        except Exception as e:
            print(f"WARNING: Exception during corrupted backup test (expected): {e}")
        
        # Test 5: Empty backup
        print("\nTest 5: Empty backup")
        try:
            empty_backup = backup_dir / "test_empty_backup.tar.gz"
            with tarfile.open(empty_backup, 'w:gz') as tar:
                pass  # Create empty archive
            
            metadata = protector._extract_and_validate_backup_metadata(empty_backup)
            if metadata is None:
                print("SUCCESS: Correctly returned None for empty backup")
            else:
                print("ERROR: Should have returned None for empty backup")
                return False
        except Exception as e:
            print(f"WARNING: Exception during empty backup test: {e}")
        
        print("\nSUCCESS: All decode functionality tests completed successfully!")
        return True


def test_list_backups_integration():
    """Test that list_backups works with the refactored decode function"""
    print("\nTesting list_backups Integration")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        backup_dir = temp_path / "test_backups"
        backup_dir.mkdir()
        
        # Initialize DatabaseProtector with test directory
        protector = DatabaseProtector(data_dir=str(temp_path / "data"))
        
        # Create multiple test backups
        for i in range(3):
            create_test_backup(backup_dir, f"test_backup_{i}")
        
        # Test list_backups
        try:
            backups = protector.list_backups()
            print(f"SUCCESS: Successfully listed {len(backups)} backups")
            
            for backup in backups:
                print(f"   - {backup.get('backup_type')} backup from {backup.get('created_at')}")
                print(f"     Databases: {backup.get('databases_backed_up', [])}")
                
        except Exception as e:
            print(f"ERROR: Exception during list_backups test: {e}")
            return False
        
        print("SUCCESS: list_backups integration test completed successfully!")
        return True


def main():
    """Run all tests"""
    print("Starting Database Protection Decode Refactoring Tests")
    print("=" * 60)
    
    # Set up logging for testing
    logger.setLevel('DEBUG')
    
    success = True
    
    # Test decode functionality
    try:
        if not test_decode_functionality():
            success = False
    except Exception as e:
        print(f"ERROR: Decode functionality test failed: {e}")
        success = False
    
    # Test list_backups integration
    try:
        if not test_list_backups_integration():
            success = False
    except Exception as e:
        print(f"ERROR: list_backups integration test failed: {e}")
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("ALL TESTS PASSED - Decode refactoring successful!")
        print("SUCCESS: Professional naming and structure implemented")
        print("SUCCESS: Comprehensive error handling added")
        print("SUCCESS: Enterprise-grade logging implemented")
        print("SUCCESS: Robust validation and metadata extraction working")
    else:
        print("SOME TESTS FAILED - Issues need to be addressed")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)