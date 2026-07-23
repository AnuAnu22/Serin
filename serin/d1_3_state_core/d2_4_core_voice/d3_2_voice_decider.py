"""
Voice Action Decider - Structured output for voice join/leave decisions.
Part of the thinking/response pipeline (Option C).
Decides if Serin should join/leave a voice channel based on conversation context.
"""
from __future__ import annotations

import json
import re
from typing import Any, cast

from serin.d1_3_state_core.d2_5_core_logger import logger


class VoiceActionDecider:
    """
    Decides if Serin should join/leave/none in voice channels.
    Uses a lightweight LLM call with structured JSON output.

    Returns: {"action": "join"|"leave"|"none", "reason": "..."}
    """

    def __init__(self, model_connector: Any) -> None:
        self.llm = model_connector
        logger.info(" Voice action decider initialized")

    async def decide(
        self,
        user_message: str,
        context: str,
        personality_state: dict[str, float] | None = None,
    ) -> dict[str, str]:
        """
        Decide voice action based on conversation context.

        Returns:
            {"action": "join" | "leave" | "none", "reason": "..."}
        """
        # Fast path: heuristic keyword check
        if not self._has_voice_intent(user_message):
            return {"action": "none", "reason": "heuristic_skip"}

        try:
            messages = self._build_messages(user_message, context, personality_state or {})
            response = await self.llm.chat_completion(
                messages=messages,
                temperature=0.1,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            decision = self._parse_decision(response)

            if decision.get("action") in ("join", "leave", "none"):
                logger.info(
                    " Voice action decided: %s (%s)",
                    decision["action"], decision.get("reason", "no reason")
                )
                return decision

            return {"action": "none", "reason": "invalid_parse"}

        except Exception as e:
            logger.error(f" Voice action decision error: {e}")
            return {"action": "none", "reason": "error"}

    def _has_voice_intent(self, message: str) -> bool:
        """Quick heuristic to skip LLM call when no voice intent."""
        keywords = [
            "vc", "voice", "join", "leave", "come", "talk",
            "chat", "call", "hangout", "speak", "audio",
            "mic", "start talking", "can you hear"
        ]
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in keywords)

    def _build_messages(
        self,
        message: str,
        context: str,
        personality: dict[str, float],
    ) -> list[dict[str, str]]:

        energy = personality.get("energy", 0.5)
        sass = personality.get("sass", 0.5)

        system_prompt = (
            "You are Serin's internal voice action system. Decide if Serin should join or leave a voice channel.\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"CURRENT STATE:\n- Energy level: {energy:.1f}/1.0\n- Sass level: {sass:.1f}/1.0\n\n"
            "RULES:\n"
            '- "join": The user explicitly or implicitly wants Serin in voice chat\n'
            '- "leave": Socially appropriate to leave\n'
            '- "none": No voice action needed\n\n'
            "OUTPUT FORMAT (JSON ONLY):\n"
            '{\n    "action": "join" | "leave" | "none",\n    "reason": "short explanation"\n}'
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]

    def _parse_decision(self, response: str) -> dict[str, str]:
        """Parse JSON decision from LLM response."""
        try:
            raw = response.strip()

            # Try to extract a complete JSON object between braces first
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                return cast(dict[str, str], json.loads(json_match.group(0)))

            # LLM output likely starts without opening brace (prompt provides {)
            # Fix: LLM often omits commas between key-value pairs on separate lines.
            # Join lines with commas, close unclosed strings, wrap in braces.

            # 1. Close any unclosed string value (odd number of quotes means one is open)
            if raw.count('"') % 2 != 0:
                raw += '"'

            # 2. Join lines with commas to handle missing-comma output
            lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
            joined = ", ".join(lines)

            # 3. Wrap in braces
            if not joined.startswith("{"):
                joined = "{" + joined
            if not joined.endswith("}"):
                joined += "}"

            return cast(dict[str, str], json.loads(joined))
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f" Failed to parse voice decision: {response[:120]}...")
            return {"action": "none", "reason": "parsing_fallback"}
