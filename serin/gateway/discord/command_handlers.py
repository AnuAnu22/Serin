"""Bot command handler functions."""
import asyncio
from typing import Any

import discord

from serin.logger import logger


async def handle_profile_command(
    message: discord.Message,
    message_manager: Any,
    stats: dict[str, Any],
) -> bool:
    """Handle !profile command. Returns True if command was handled."""
    if not message.content.lower().startswith("!profile"):
        return False

    stats['commands_executed'] += 1
    logger.info(f"Command: !profile from {message.author.display_name}")

    try:
        mentioned_users = message.mentions
        target_id = str(mentioned_users[0].id) if mentioned_users else str(message.author.id)
        target_name = mentioned_users[0].display_name if mentioned_users else message.author.display_name

        profile = message_manager.get_user_profile(target_id)

        if profile:
            traits = profile.get('personality_traits', [])[:5]
            interests = profile.get('interests', [])[:5]

            response = (
                f"**Profile: {target_name}**\n"
                f"Traits: {', '.join(traits) or 'None detected'}\n"
                f"Interests: {', '.join(interests) or 'None detected'}\n"
                f"Messages: {profile.get('total_messages', 0)}\n"
                f"Avg. Length: {round(profile.get('avg_message_length', 0), 1)} chars\n"
                f"Last seen: {profile.get('last_seen', 'Unknown')}"
            )
        else:
            response = f"No profile data found for {target_name}."

        await message.channel.send(response)

    except Exception as e:
        logger.error(f"Error in !profile command: {e}")
        await message.channel.send("Error retrieving profile.")

    return True


async def handle_stats_command(
    message: discord.Message,
    message_manager: Any,
    background_processor: Any,
    passive_monitor: Any,
    message_crawler: Any,
    stats: dict[str, Any],
) -> bool:
    """Handle !stats command. Returns True if command was handled."""
    if not message.content.lower().startswith("!stats"):
        return False

    stats['commands_executed'] += 1
    logger.info(f"Command: !stats from {message.author.display_name}")

    try:
        uptime = asyncio.get_running_loop().time() - stats['start_time']
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)

        mem_stats = message_manager.get_memory_stats()
        mgr_stats = mem_stats.get('manager_stats', {})

        bg_stats = background_processor.get_stats() if background_processor else {}
        passive_stats = passive_monitor.get_stats() if passive_monitor else {}
        voice_stats = message_manager.voice_tracker.get_stats()
        crawler_stats = message_crawler.get_stats() if message_crawler else {}

        response = (
            "**Bot Statistics**\n"
            f"Uptime: {hours}h {minutes}m\n"
            f"Messages Received: {stats['messages_received']}\n"
            f"Active Processed: {stats['messages_processed']}\n"
            f"Passive Monitored: {stats['passive_messages']}\n"
            f"Responses Generated: {mgr_stats.get('responses_generated', 0)}\n"
            f"Corrections Learned: {mgr_stats.get('corrections_detected', 0)}\n\n"
            "**Memory System**\n"
            f"Total Memories: {mem_stats.get('total_memories', 0)}\n"
            f"Total Users: {mem_stats.get('total_users', 0)}\n"
            f"Strong Relationships: {mem_stats.get('strong_relationships', 0)}\n\n"
            "**Background Processing**\n"
            f"Queue Size: {bg_stats.get('queue_size', 0)}\n"
            f"Summaries Created: {bg_stats.get('summaries_created', 0)}\n"
            f"Processed: {bg_stats.get('total_processed', 0)}\n\n"
            "**Voice Tracking**\n"
            f"Users in Voice: {voice_stats.get('users_in_voice', 0)}\n"
            f"Active Sessions: {voice_stats.get('active_sessions', 0)}\n\n"
            "**Cross-Server**\n"
            f"Servers: {passive_stats.get('servers_monitored', 0)}\n"
            f"Channels: {passive_stats.get('channels_monitored', 0)}\n\n"
            "**Message Crawler**\n"
            f"Quick Syncs: {crawler_stats.get('quick_syncs', 0)}\n"
            f"Deep Validations: {crawler_stats.get('deep_validations', 0)}\n"
            f"Messages Backfilled: {crawler_stats.get('messages_backfilled', 0)}\n"
            f"Gaps Found: {crawler_stats.get('gaps_found', 0)}\n\n"
        )

        await message.channel.send(response)

    except Exception as e:
        logger.error(f"Error in !stats command: {e}")
        await message.channel.send("Error retrieving stats.")

    return True


async def handle_help_command(
    message: discord.Message,
    stats: dict[str, Any],
) -> bool:
    """Handle !help command. Returns True if command was handled."""
    if not message.content.lower().startswith("!help"):
        return False

    stats['commands_executed'] += 1

    response = (
        "**Serin Bot Commands**\n"
        "`!profile [@user]` - View personality profile\n"
        "`!stats` - View bot statistics\n"
        "`!help` - Show this help message\n\n"
        "**How I Work:**\n"
        "- I monitor ALL channels across ALL servers (one shared memory)\n"
        "- I learn from everything I see\n"
        "- I only respond in allowed channels\n"
        "- Mention me with @ for immediate responses\n\n"
        "**Features:**\n"
        "Multi-Model Support - Works with any LLM\n"
        "Temporal Awareness - Understands 'last Tuesday'\n"
        "Correction Learning - Learns when you correct me\n"
        "Voice Tracking - Aware of voice channel activity"
    )
    await message.channel.send(response)
    return True
