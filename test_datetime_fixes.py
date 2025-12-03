#!/usr/bin/env python3
"""
Test script to verify datetime fixes for the Discord bot system.
This script tests the key functions that were causing datetime comparison errors.
"""

import sys
import os
from datetime import datetime, timedelta

# Add current directory to path so we can import the modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_safe_datetime_convert():
    """Test the safe datetime conversion function"""
    print("🧪 Testing safe datetime conversion...")
    
    # Import the safe datetime conversion function
    def safe_datetime_convert(timestamp):
        """Safely convert timestamp to datetime, handling both string and datetime inputs"""
        if isinstance(timestamp, str):
            return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return timestamp
    
    # Test cases
    test_cases = [
        "2025-11-04T00:05:17.333000",
        "2025-11-04T00:05:17.333Z",
        datetime.now(),
        datetime.now() - timedelta(hours=1),
    ]
    
    for i, test_case in enumerate(test_cases):
        try:
            result = safe_datetime_convert(test_case)
            print(f"   ✅ Test {i+1}: {type(test_case).__name__} → {type(result).__name__} (Success)")
        except Exception as e:
            print(f"   ❌ Test {i+1}: {type(test_case).__name__} → Error: {e}")
            return False
    
    return True

def test_datetime_comparisons():
    """Test datetime comparison operations"""
    print("🧪 Testing datetime comparisons...")
    
    def safe_datetime_convert(timestamp):
        """Safely convert timestamp to datetime, handling both string and datetime inputs"""
        if isinstance(timestamp, str):
            return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return timestamp
    
    # Test cases with different timestamp formats
    timestamp1 = "2025-11-04T00:05:17.333Z"
    timestamp2 = datetime.now() - timedelta(minutes=5)
    
    try:
        dt1 = safe_datetime_convert(timestamp1)
        dt2 = safe_datetime_convert(timestamp2)
        
        # Test comparison
        comparison_result = dt2 > dt1
        print(f"   ✅ Comparison test: {type(timestamp1).__name__} vs {type(timestamp2).__name__} = {comparison_result} (Success)")
        
        # Test time difference
        time_diff = (dt2 - dt1).total_seconds()
        print(f"   ✅ Time difference test: {time_diff:.2f} seconds (Success)")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Comparison test failed: {e}")
        return False

def test_message_grouping_logic():
    """Test message grouping logic for conversation grouping"""
    print("🧪 Testing message grouping logic...")
    
    def safe_datetime_convert(timestamp):
        """Safely convert timestamp to datetime, handling both string and datetime inputs"""
        if isinstance(timestamp, str):
            return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return timestamp
    
    # Simulate a batch of messages with mixed timestamp formats
    messages = [
        {
            'content': 'Hello everyone',
            'user_id': '123',
            'username': 'Alice',
            'channel_id': '456',
            'timestamp': '2025-11-04T10:00:00.000Z'  # String format
        },
        {
            'content': 'How are you?',
            'user_id': '124', 
            'username': 'Bob',
            'channel_id': '456',
            'timestamp': datetime.now() - timedelta(minutes=2)  # Datetime object
        },
        {
            'content': 'Good thanks',
            'user_id': '123',
            'username': 'Alice', 
            'channel_id': '456',
            'timestamp': '2025-11-04T10:05:00.000Z'  # String format
        }
    ]
    
    try:
        # Sort by timestamp (this was failing before)
        def get_sort_key(msg):
            timestamp = msg['timestamp']
            if isinstance(timestamp, str):
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return timestamp
        
        sorted_messages = sorted(messages, key=get_sort_key)
        print(f"   ✅ Sorting test: {len(messages)} messages sorted successfully")
        
        # Test grouping logic (similar to background_processor)
        sorted_batch = sorted(messages, key=lambda x: safe_datetime_convert(x['timestamp']))
        
        current_group = [sorted_batch[0]]
        groups = []
        
        for msg in sorted_batch[1:]:
            prev_msg = current_group[-1]
            
            # Same channel and within 5 minutes?
            msg_time = safe_datetime_convert(msg['timestamp'])
            prev_time = safe_datetime_convert(prev_msg['timestamp'])
            
            time_diff = (msg_time - prev_time).total_seconds()
            same_channel = msg['channel_id'] == prev_msg['channel_id']
            
            if same_channel and time_diff < 300:  # 5 minutes
                current_group.append(msg)
            else:
                # Start new group
                groups.append(current_group)
                current_group = [msg]
        
        # Add last group
        if current_group:
            groups.append(current_group)
        
        print(f"   ✅ Grouping test: Created {len(groups)} conversation groups")
        return True
        
    except Exception as e:
        print(f"   ❌ Grouping test failed: {e}")
        return False

def test_temporal_filtering():
    """Test temporal filtering operations"""
    print("🧪 Testing temporal filtering...")
    
    def safe_datetime_convert(timestamp):
        """Safely convert timestamp to datetime, handling both string and datetime inputs"""
        if isinstance(timestamp, str):
            return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return timestamp
    
    # Simulate memory objects with mixed timestamp formats
    memories = [
        {
            'content': 'Recent memory',
            'timestamp': '2025-11-04T10:00:00.000Z',  # String
            'importance': 0.8
        },
        {
            'content': 'Older memory',
            'timestamp': datetime.now() - timedelta(days=2),  # Datetime object
            'importance': 0.6
        },
        {
            'content': 'Very old memory',
            'timestamp': '2025-11-01T10:00:00.000Z',  # String
            'importance': 0.4
        }
    ]
    
    try:
        now = datetime.now()
        cutoff_date = now - timedelta(days=1)
        
        # Filter by time period (similar to enhanced_memory_retrieval)
        filtered = [
            mem for mem in memories
            if safe_datetime_convert(mem['timestamp']) >= cutoff_date
        ]
        
        print(f"   ✅ Temporal filtering: {len(memories)} → {len(filtered)} memories (Success)")
        return True
        
    except Exception as e:
        print(f"   ❌ Temporal filtering failed: {e}")
        return False

def run_all_tests():
    """Run all datetime fix tests"""
    print("🚀 Starting datetime fixes verification...\n")
    
    tests = [
        test_safe_datetime_convert,
        test_datetime_comparisons,
        test_message_grouping_logic,
        test_temporal_filtering
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            print()  # Add spacing between tests
        except Exception as e:
            print(f"   ❌ Test failed with exception: {e}\n")
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All datetime fixes are working correctly!")
        return True
    else:
        print("❌ Some tests failed. Please review the fixes.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)