"""Bot event and maintenance handlers."""
import asyncio
from typing import Any

import discord

from serin.config.config import config
from serin.gateway.discord.bot import client, stats
from serin.logger import logger


@client.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    """Handle voice state changes - track + auto-join decisions"""
    from serin.gateway.discord import bot_pipeline_init as bp

    try:
        stats['voice_events'] += 1

        if bp.message_manager and hasattr(bp.message_manager, 'voice_tracker'):
            await bp.message_manager.voice_tracker.on_voice_update(member, before, after)

        if after.channel and not before.channel:
            if bp.voice_behavior_manager and bp.voice_listener:
                await bp.voice_behavior_manager.on_user_joined_vc(
                    user_id=str(member.id),
                    username=member.display_name,
                    guild_id=after.channel.guild.id,
                    channel_id=after.channel.id,
                    channel_name=after.channel.name,
                )

    except Exception as e:
        logger.exception(f"Error in voice state update: {e}")


@client.event
async def on_error(event: str, *args: Any, **kwargs: Any) -> None:
    """Handle Discord.py errors"""
    stats['errors'] += 1
    logger.exception(f"Discord error in event '{event}'")


async def run_maintenance() -> None:
    """Periodic maintenance task"""
    from serin.gateway.discord import bot_pipeline_init as bp

    maintenance_count = 0
    while True:
        try:
            await asyncio.sleep(config.MAINTENANCE_INTERVAL_HOURS * 3600)
            maintenance_count += 1
            logger.info("Running periodic maintenance...")

            if bp.background_processor:
                await bp.background_processor.run_maintenance()

            try:
                backup_path = bp.db_protector.create_backup(backup_type="scheduled")
                logger.info(f"Scheduled backup created: {backup_path}")
            except Exception as e:
                logger.error(f"Backup failed: {e}")

            if bp.message_manager:
                try:
                    stats_before = bp.message_manager.get_memory_stats()
                    logger.info(f"Before: {stats_before.get('total_memories', 0)} memories")

                    if hasattr(bp.message_manager.memory, 'cleanup_old_memories'):
                        cleaned = bp.message_manager.memory.cleanup_old_memories(
                            days_old=90, min_importance=0.3,
                        )
                        logger.info(f"Removed {cleaned} old memories")

                    stats_after = bp.message_manager.get_memory_stats()
                    logger.info(f"After: {stats_after.get('total_memories', 0)} memories")
                except Exception as e:
                    logger.error(f"Memory cleanup failed: {e}")

            logger.info(f"Maintenance task #{maintenance_count} complete!")

        except Exception as e:
            logger.error(f"Error in maintenance task: {e}")
            await asyncio.sleep(3600)
