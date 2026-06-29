"""
Voice Action Decider - Structured output for voice join/leave decisions.
Part of the thinking/response pipeline (Option C).
Decides if Serin should join/leave a voice channel based on conversation context.
"""
import json
import re
from typing import Any, Dict, Optional
from logger_config import logger


class VoiceActionDecider:
    """
    Decides if Serin should join/leave/none in voice channels.
    Uses a lightweight LLM call with structured JSON output.
    
    Returns: {"action": "join"|"leave"|"none", "reason": "..."}
    """

    def __init__(self, model_connector: Any) -> None:
        self.llm = model_connector
        logger.info("✅ Voice action decider initialized")

    async def decide(
        self,
        user_message: str,
        context: str,
        personality_state: Optional[Dict[str, float]] = None,
    ) -> Dict[str, str]:
        """
        Decide voice action based on conversation context.
        
        Returns:
            {"action": "join" | "leave" | "none", "reason": "..."}
        """
        # Fast path: heuristic keyword check
        if not self._has_voice_intent(user_message):
            return {"action": "none", "reason": "heuristic_skip"}

        try:
            prompt = self._build_prompt(user_message, context, personality_state or {})
            response = await self.llm.send_input(
                prompt=prompt,
                temperature=0.1,
                max_tokens=200,
            )
            decision = self._parse_decision(response)

            if decision.get("action") in ("join", "leave", "none"):
                logger.info(
                    "🎙️ Voice action decided: %s (%s)",
                    decision["action"], decision.get("reason", "no reason")
                )
                return decision

            return {"action": "none", "reason": "invalid_parse"}

        except Exception as e:
            logger.error(f"❌ Voice action decision error: {e}")
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

    def _build_prompt(
        self,
        message: str,
        context: str,
        personality: Dict[str, float],
    ) -> str:
        energy = personality.get("energy_level", 0.5)
        sass = personality.get("sass_level", 0.5)

        return f"""You are Serin's internal voice action system. Decide if Serin should join or leave a voice channel.

CONTEXT:
{context}

USER MESSAGE: "{message}"

CURRENT STATE:
- Energy level: {energy:.1f}/1.0
- Sass level: {sass:.1f}/1.0

RULES:
- "join": The user explicitly or implicitly wants Serin in voice chat
- "leave": It's socially appropriate to leave (conversation winding down, been in VC long)
- "none": No voice action needed

OUTPUT FORMAT (JSON ONLY):
{{
    "action": "join" | "leave" | "none",
    "reason": "short explanation"
}}

RESPONSE:
{{"""

    def _parse_decision(self, response: str) -> Dict[str, str]:
        """Parse JSON decision from LLM response."""
        try:
            raw = response.strip()

            # Try to extract a complete JSON object between braces first
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))

            # LLM output likely starts without opening brace (prompt provides {)
            # Order matters: close unclosed string BEFORE wrapping in braces

            # 1. Close any unclosed string value (odd number of quotes means one is open)
            if raw.count('"') % 2 != 0:
                raw += '"'

            # 2. Wrap in braces
            if not raw.startswith("{"):
                raw = "{" + raw
            if not raw.endswith("}"):
                raw += "}"

            return json.loads(raw)
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"⚠️ Failed to parse voice decision: {response[:120]}...")
            return {"action": "none", "reason": "parsing_fallback"}
