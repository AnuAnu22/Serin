#!/usr/bin/env python3
"""
Debug message backfilling - Test message retrieval directly
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from logger_config import logger
import logging
logging.basicConfig(level=logging.INFO)

async def test_message_retrieval_direct():
    """Test message retrieval from Discord directly"""
    try:
        import discord
        
        # Import bot client (this might fail if not running)
        from discord_bot import client
        
        print("🔍 Testing message retrieval from connected channels...")
        
        # Test a few channels with detailed debugging
        for guild in client.guilds[:2]:  # Test first 2 servers only
            print(f"\n📡 Server: {guild.name} (ID: {guild.id})")
            
            for channel in guild.text_channels[:3]:  # Test first 3 channels
                print(f"\n   🔍 Testing channel: #{channel.name} (ID: {channel.id})")
                
                try:
                    # Check permissions first
                    me = guild.me
                    permissions = channel.permissions_for(me)
                    print(f"      🔑 Permissions:")
                    print(f"         - View Channel: {permissions.view_channel}")
                    print(f"         - Read Message History: {permissions.read_message_history}")
                    print(f"         - Read Message Content: {permissions.read_message_content}")
                    
                    if not permissions.view_channel or not permissions.read_message_history:
                        print(f"      ❌ Insufficient permissions for #{channel.name}")
                        continue
                    
                    # Try to get message count using different methods
                    print(f"      📊 Getting message count...")
                    
                    # Method 1: Get latest message
                    latest_messages = []
                    async for message in channel.history(limit=5, oldest_first=False):
                        latest_messages.append(message)
                        if len(latest_messages) >= 3:
                            break
                    
                    print(f"      📥 Found {len(latest_messages)} recent messages (limit 5)")
                    
                    # Show message details
                    for i, msg in enumerate(latest_messages):
                        is_bot = "🤖 BOT" if msg.author.bot else "👤 USER"
                        content_preview = msg.content[:50] if msg.content else "[no content]"
                        print(f"         Message {i+1}: {msg.author.name} ({is_bot}) - {content_preview}...")
                        print(f"                   ID: {msg.id}, Timestamp: {msg.created_at}")
                    
                    # Method 2: Try to get oldest messages
                    oldest_messages = []
                    try:
                        async for message in channel.history(limit=10, oldest_first=True):
                            oldest_messages.append(message)
                            if len(oldest_messages) >= 3:
                                break
                    except Exception as e:
                        print(f"      ⚠️ Couldn't fetch oldest messages: {e}")
                    
                    print(f"      📅 Found {len(oldest_messages)} oldest messages")
                    
                    # Method 3: Test message counting
                    total_count = 0
                    try:
                        async for message in channel.history(limit=100):
                            total_count += 1
                            if total_count >= 50:  # Don't count too many
                                break
                    except Exception as e:
                        print(f"      ⚠️ Error counting messages: {e}")
                    
                    print(f"      📊 Total messages in channel (sample): {total_count}")
                    
                    # Check if channel is empty
                    if len(latest_messages) == 0:
                        print(f"      ⚠️ Channel appears to be empty")
                    else:
                        print(f"      ✅ Channel has messages - backfill should work")
                    
                except discord.Forbidden:
                    print(f"      ❌ Forbidden access to #{channel.name} (check bot permissions)")
                except discord.HTTPException as e:
                    print(f"      ❌ HTTP error accessing #{channel.name}: {e}")
                except Exception as e:
                    print(f"      ❌ Error accessing #{channel.name}: {e}")
                    import traceback
                    traceback.print_exc()
                    
                # Rate limiting
                await asyncio.sleep(2)
                
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("⚠️ Bot might not be running. Start discord_bot.py first.")
    except Exception as e:
        print(f"❌ General error: {e}")
        import traceback
        traceback.print_exc()

async def test_memory_system():
    """Test memory system state"""
    try:
        from memory_system import UnifiedMemorySystem
        
        print("\n💾 Testing memory system state...")
        memory = UnifiedMemorySystem()
        
        # Check database state
        cursor = memory.conn.cursor()
        
        # Count total messages in database
        cursor.execute("SELECT COUNT(*) FROM recent_messages")
        total_db_messages = cursor.fetchone()[0]
        print(f"📊 Total messages in database: {total_db_messages}")
        
        # Get sample of recent messages
        if total_db_messages > 0:
            cursor.execute("""
                SELECT rm.message_id, rm.username, rm.content, rm.channel_id, rm.timestamp,
                       g.name as guild_name, c.name as channel_name
                FROM recent_messages rm
                LEFT JOIN (
                    SELECT guild_id, channel_id, channel.name
                    FROM (
                        SELECT guild.id as guild_id, channel.id as channel_id, 
                               RANK() OVER (PARTITION BY channel.id ORDER BY rm.timestamp DESC) as rn
                        FROM recent_messages rm2, (
                            SELECT guild.id, channel.id as channel_id
                            FROM guild, channel
                        ) channel
                        LEFT JOIN channel ON True
                    ) rnk, guild, channel
                ) c ON rm.channel_id = c.channel_id
                ORDER BY rm.timestamp DESC LIMIT 5
            """)
            recent = cursor.fetchall()
            
            print(f"📝 Most recent messages in database:")
            for msg in recent:
                print(f"   {msg['username']}: {msg['content'][:50]}... (Channel: {msg['channel_name']})")
        
        return True
        
    except Exception as e:
        print(f"❌ Memory system error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function"""
    print("🧪 Debugging Message Backfilling")
    print("=" * 50)
    
    # Test 1: Memory system
    print("\n🔍 Test 1: Memory System State")
    await test_memory_system()
    
    print("\n" + "=" * 50)
    
    # Test 2: Message retrieval (only if bot is running)
    print("\n🔍 Test 2: Message Retrieval from Discord")
    await test_message_retrieval_direct()
    
    print(f"\n{'=' * 50}")
    print("✅ Debugging complete!")

if __name__ == "__main__":
    asyncio.run(main())