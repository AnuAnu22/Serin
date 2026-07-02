"""
Mention Translator - Converts Discord mentions bidirectionally
INPUT:  <@1378682870876340395> → @Rin (for bot understanding)
OUTPUT: @Rin → <@1378682870876340395> (for Discord mentions)
"""
from __future__ import annotations

import re
from typing import Any

import discord

from serin.d1_3_state_core.logger import logger


class MentionTranslator:
    def __init__(self, discord_client: discord.Client) -> None:
        """
        Initialize mention translator with Discord client.

        Args:
            discord_client: Discord.py client instance
        """
        self.client = discord_client
        self.user_cache: dict[str, dict[str, str]] = {}  # {user_id: {name, global_name, mention}}
        self.name_to_id_cache: dict[str, str] = {}  # {username: user_id}

        logger.info(" MentionTranslator initialized")

    def update_cache(self, user: Any) -> None:
        """
        Update user cache from Discord user object.

        Args:
            user: Discord.User object
        """
        user_id = str(user.id)
        username = user.name.lower()  # Normalize to lowercase
        display_name = (user.global_name or user.name).lower()

        self.user_cache[user_id] = {
            'name': user.name,
            'global_name': user.global_name or user.name,
            'display_name': display_name,
            'mention': f"<@{user.id}>"
        }

        # Bidirectional lookup
        self.name_to_id_cache[username] = user_id
        self.name_to_id_cache[display_name] = user_id

        logger.debug(f" Cached user: {user.name} ({user_id})")

    def clean_for_bot(self, text: str, message: discord.Message) -> str:
        """
        Convert Discord mentions <@123> to readable @username for bot.
        This makes memories human-readable and LLM-understandable.

        Args:
            text: Message content with Discord mentions
            message: Discord.Message object (to access guild/mentions)

        Returns:
            Cleaned text with @username instead of <@id>
        """
        if not text:
            return text

        # Pattern: <@123456789> or <@!123456789> (! is for nickname mentions)
        mention_pattern = r'<@!?(\d+)>'

        def replace_mention(match: re.Match[str]) -> str:
            user_id = match.group(1)

            # Try cache first
            if user_id in self.user_cache:
                return f"@{self.user_cache[user_id]['global_name']}"

            # Try from message mentions
            if hasattr(message, 'mentions'):
                for user in message.mentions:
                    if str(user.id) == user_id:
                        self.update_cache(user)
                        return f"@{user.global_name or user.name}"

            # Try to fetch from guild
            if hasattr(message, 'guild') and message.guild:
                try:
                    member = message.guild.get_member(int(user_id))
                    if member:
                        self.update_cache(member)
                        return f"@{member.global_name or member.name}"
                except Exception as e:
                    logger.debug(f"Failed to get guild member: {e}")
                    pass

            # Fallback: keep original mention if we can't resolve
            logger.warning(f" Could not resolve mention <@{user_id}>")
            return f"@unknown_user_{user_id[:4]}"

        cleaned_text = re.sub(mention_pattern, replace_mention, text)

        if cleaned_text != text:
            logger.debug(f" Cleaned mentions: '{text[:50]}' → '{cleaned_text[:50]}'")

        return cleaned_text

    def restore_for_discord(self, text: str, guild: discord.Guild | None = None) -> str:
        """
        Convert @username back to Discord mentions <@123> for sending.
        This allows bot to mention users properly.

        Args:
            text: Bot response with @username
            guild: Discord.Guild object (optional, for member lookup)

        Returns:
            Text with Discord mention format <@id>
        """
        if not text:
            return text

        # Pattern: @username (word boundary aware)
        # Matches @Rin but not email@example.com
        mention_pattern = r'(?<!\w)@(\w+)'

        def replace_username(match: re.Match[str]) -> str:
            username = match.group(1).lower()

            # Check cache
            if username in self.name_to_id_cache:
                user_id = self.name_to_id_cache[username]
                if user_id in self.user_cache:
                    return self.user_cache[user_id]['mention']

            # Try guild members if available
            if guild:
                try:
                    for member in guild.members:
                        if member.name.lower() == username or (member.global_name and member.global_name.lower() == username):
                            self.update_cache(member)
                            return f"<@{member.id}>"
                except Exception as e:
                    logger.debug(f"Failed to iterate guild members: {e}")
                    pass

            # Can't resolve - leave as @username (won't ping but readable)
            logger.debug(f" Could not resolve username @{username} to mention")
            return f"@{username}"

        restored_text = re.sub(mention_pattern, replace_username, text)

        if restored_text != text:
            logger.debug(f" Restored mentions: '{text[:50]}' → '{restored_text[:50]}'")

        return restored_text

    def clean_bot_self_mention(self, text: str) -> str:
        """
        Remove bot's own mention from text (so it doesn't see '@Serin' in memory).

        Args:
            text: Message content

        Returns:
            Text without bot mention
        """
        if not self.client.user:
            return text

        bot_id = str(self.client.user.id)
        bot_mention_pattern = rf'<@!?{bot_id}>\s*'

        cleaned = re.sub(bot_mention_pattern, '', text).strip()
        return cleaned

    def get_user_info(self, user_id: str) -> dict[str, str] | None:
        """
        Get cached user info by ID.

        Args:
            user_id: User ID as string

        Returns:
            Dict with name, global_name, display_name, mention
        """
        return self.user_cache.get(user_id)

    def get_user_id(self, username: str) -> str | None:
        """
        Get user ID by username.

        Args:
            username: Username (case-insensitive)

        Returns:
            User ID as string or None
        """
        return self.name_to_id_cache.get(username.lower())

    def cache_guild_members(self, guild: discord.Guild) -> int:
        """
        Preload guild members into cache (call on bot ready).

        Args:
            guild: Discord.Guild object

        Returns:
            Number of members cached
        """
        count = 0
        try:
            for member in guild.members:
                self.update_cache(member)
                count += 1
            logger.info(f" Cached {count} members from {guild.name}")
        except Exception as e:
            logger.error(f" Error caching guild members: {e}")

        return count

    def get_stats(self) -> dict[str, int]:
        """Get translator statistics"""
        return {
            'cached_users': len(self.user_cache),
            'name_mappings': len(self.name_to_id_cache)
        }
