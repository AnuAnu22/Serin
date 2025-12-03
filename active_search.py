"""
Active Search Module - The "Thinking" Brain
Decides when to search and what to search for.
"""
import json
import re
from typing import Dict, Optional, Tuple
from logger_config import logger
from models.model_interface import ModelInterface

class ActiveSearch:
    def __init__(self, model_connector: ModelInterface):
        self.llm = model_connector

    async def analyze_need_to_search(self, user_message: str, recent_context: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Analyze if a search is needed and generate a query.
        Returns: (needs_search, query, reason)
        """
        
        # Heuristic Check (Fast Path)
        if not self._passes_heuristics(user_message):
            return False, None, "heuristic_skip"

        # LLM Check (Slow Path)
        try:
            prompt = self._build_thinking_prompt(user_message, recent_context)
            
            # Use a lower temperature for logic
            response = await self.llm.send_input(
                prompt=prompt,
                temperature=0.1,
                max_tokens=150,
                stop=["}"] # Stop at end of JSON
            )
            
            # Parse JSON output
            decision = self._parse_decision(response)
            
            if decision.get('search_needed'):
                return True, decision.get('query'), decision.get('reason')
            else:
                return False, None, decision.get('reason', 'llm_decided_no')
                
        except Exception as e:
            logger.error(f"❌ Active Search Error: {e}")
            return False, None, "error"

    def _passes_heuristics(self, message: str) -> bool:
        """Quick check to see if we should even bother asking the LLM"""
        msg_len = len(message.strip())
        
        # Too short?
        if msg_len < 10:
            return False
            
        # Purely emotional/social? (lol, haha, thanks)
        social_words = {'lol', 'lmao', 'haha', 'thanks', 'thx', 'cool', 'ok', 'okay', 'nice'}
        if message.lower().strip() in social_words:
            return False
            
        # Contains question or recall keywords?
        keywords = {'who', 'what', 'where', 'when', 'why', 'how', 'remember', 'recall', 'think', 'know', 'last time', 'said'}
        has_keyword = any(kw in message.lower() for kw in keywords)
        has_question = '?' in message
        
        return has_keyword or has_question or msg_len > 30

    def _build_thinking_prompt(self, message: str, context: str) -> str:
        return f"""You are the internal monologue of an AI. Decide if you need to search your long-term memory to answer the user.

CONTEXT:
{context}

USER MESSAGE: "{message}"

TASK:
1. Do you have enough info in the CONTEXT to answer?
2. Is the user asking about a past event, fact, or conversation not shown here?
3. If YES to #2, generate a specific search query.

OUTPUT FORMAT (JSON ONLY):
{{
    "search_needed": true/false,
    "query": "specific search terms" or null,
    "reason": "short explanation"
}}

RESPONSE:
{{"""

    def _parse_decision(self, response: str) -> Dict:
        """Parse the LLM response into a dict"""
        try:
            # Clean up response to ensure valid JSON
            cleaned = response.strip()
            if not cleaned.endswith('}'):
                cleaned += '}'
            if not cleaned.startswith('{'):
                cleaned = '{' + cleaned
                
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"⚠️ Failed to parse thinking response: {response}")
            # Fallback: simple text search if it looks like a query
            if len(response) < 50 and " " in response:
                 return {"search_needed": True, "query": response, "reason": "parsing_fallback"}
            return {"search_needed": False}
