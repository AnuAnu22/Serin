#!/usr/bin/env python3
"""
Simple test to verify human-like bot improvements
"""

import sys
import os
sys.path.append('/home/user1/BackupL/Backup')

from enhanced_memory_context import ImprovedSystemPrompt
from bot_personality import BotPersonality

def main():
    print("TESTING HUMAN-LIKE BOT IMPROVEMENTS")
    print("="*60)
    
    # Test 1: System Prompt
    print("\n1. Testing System Prompt:")
    prompt = ImprovedSystemPrompt.get_enhanced_system_prompt()
    print(f"Length: {len(prompt)} chars")
    print(f"Contains 'Hey': {'Hey' in prompt}")
    print(f"Contains casual language: {any(word in prompt.lower() for word in ['honestly', 'you know', 'chill'])}")
    
    # Test 2: Personality Context
    print("\n2. Testing Personality Context:")
    try:
        personality = BotPersonality(":memory:")
        context = personality.get_personality_context()
        print(f"Length: {len(context)} chars")
        print(f"Content: '{context}'")
        print(f"No bullet points: {'- ' not in context}")
        print(f"Natural tone: {any(word in context.lower() for word in ['huge', 'into', 'not into'])}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "="*60)
    print("TEST COMPLETE")

if __name__ == "__main__":
    main()