#!/usr/bin/env python3
"""
Test script to verify the human-like improvements to the bot's system.
"""

import sys
import os
sys.path.append('/home/user1/BackupL/Backup')

from enhanced_memory_context import ImprovedSystemPrompt
from bot_personality import BotPersonality
from conversation_context_builder import ConversationContextBuilder
from memory_system import UnifiedMemorySystem

def test_system_prompt():
    """Test the new human-like system prompt"""
    print("="*60)
    print(" TESTING SYSTEM PROMPT")
    print("="*60)
    
    prompt = ImprovedSystemPrompt.get_enhanced_system_prompt()
    print("New System Prompt:")
    print(prompt)
    print()
    
    # Check if it sounds more human
    human_indicators = ['hey', 'got', 'try to be', 'you know', 'honestly']
    human_score = sum(1 for word in human_indicators if word.lower() in prompt.lower())
    print(f"Human-likeness score: {human_score}/5 (higher is better)")
    
    return prompt

def test_personality_context():
    """Test the new natural personality expressions"""
    print("\n" + "="*60)
    print(" TESTING PERSONALITY CONTEXT")
    print("="*60)
    
    try:
        # Create a temporary personality system
        personality = BotPersonality(":memory:")
        
        context = personality.get_personality_context()
        print("Personality Context:")
        print(f"'{context}'")
        print()
        
        # Check if it sounds natural (no bullet points, formal structure)
        if context and not any(indicator in context.lower() for indicator in ['your preferences:', '- ', 'bullet points']):
            print(" Personality context sounds natural (no robotic formatting)")
        else:
            print(" Still has robotic formatting")
            
        return context
        
    except Exception as e:
        print(f"Error testing personality: {e}")
        return None

def test_context_formatting():
    """Test the new natural context formatting"""
    print("\n" + "="*60)
    print(" TESTING CONTEXT FORMATTING")
    print("="*60)
    
    try:
        # Create a mock memory system and context
        memory = UnifiedMemorySystem()
        builder = ConversationContextBuilder(memory)
        
        # Mock context data
        mock_context = {
            'recent_conversation': [
                {'username': 'Alice', 'content': 'Hey how\'s it going?'},
                {'username': 'Bob', 'content': 'Pretty good thanks!'}
            ],
            'relevant_memories': [
                {
                    'timestamp': '2025-11-01T10:00:00',
                    'content': 'talking about movies'
                }
            ],
            'profiles': {
                'user123': {
                    'username': 'Alice',
                    'personality_traits': ['funny', 'smart'],
                    'interests': ['movies', 'music']
                }
            },
            'relationships': [],
            'time_context': {}
        }
        
        formatted = builder.format_context_for_llm(mock_context)
        print("Formatted Context:")
        print(formatted)
        print()
        
        # Check for natural language indicators
        natural_phrases = ['what we were just talking about', 'oh yeah, and i remember', 'people in this chat']
        natural_score = sum(1 for phrase in natural_phrases if phrase.lower() in formatted.lower())
        print(f"Natural language score: {natural_score}/3 (higher is better)")
        
        if natural_score > 0:
            print(" Context formatting sounds natural")
        else:
            print(" Still sounds robotic")
            
        return formatted
        
    except Exception as e:
        print(f"Error testing context formatting: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Run all tests"""
    print(" TESTING HUMAN-LIKE BOT IMPROVEMENTS")
    print("="*80)
    
    # Test each component
    prompt = test_system_prompt()
    personality = test_personality_context()
    context = test_context_formatting()
    
    # Summary
    print("\n" + "="*60)
    print(" SUMMARY")
    print("="*60)
    
    improvements = []
    
    if prompt and len(prompt) > 100:
        improvements.append(" System prompt updated")
    else:
        improvements.append(" System prompt needs work")
        
    if personality and 'bullet' not in personality.lower():
        improvements.append(" Personality expressions naturalized")
    else:
        improvements.append(" Personality still robotic")
        
    if context and 'what we were just talking about' in context.lower():
        improvements.append(" Context formatting humanized")
    else:
        improvements.append(" Context still robotic")
    
    for improvement in improvements:
        print(improvement)
    
    print(f"\n Overall: {sum(1 for imp in improvements if imp.startswith(''))}/3 improvements successful")
    
    if all(imp.startswith('') for imp in improvements):
        print("\n All improvements successful! Bot should sound much more human now.")
    else:
        print("\n  Some improvements need more work.")

if __name__ == "__main__":
    main()