"""
Active Search Module - The "Thinking" Brain
Decides when to search and what to search for.
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from serin.state.logger import logger
from serin.state.model_system.interface import ModelInterface

class ActiveSearch:
    def __init__(self, model_connector: ModelInterface) -> None:
        self.llm = model_connector

    async def analyze_need_to_search(self, user_message: str, recent_context: str, previous_results: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Analyze if a search is needed and generate a query.
        If previous_results is provided, it decides if MORE search is needed.
        Returns: (needs_search, query, reason)
        """
        
        # Heuristic Check (Fast Path) - Only on first pass
        if not previous_results and not self._passes_heuristics(user_message):
            return False, None, "heuristic_skip"

        # LLM Check (Slow Path)
        try:
            prompt = self._build_thinking_prompt(user_message, recent_context, previous_results)
            
            # Use a lower temperature for logic
            response = await self.llm.send_input(
                prompt=prompt,
                temperature=0.1,
                max_tokens=300,  # Increased for thinking models
                stop=["}"] # Stop at end of JSON
            )
            
            # For thinking models, extract content after </think> tag
            if '</think>' in response:
                response = response.split('</think>')[-1].strip()
            
            # Parse JSON output
            decision = self._parse_decision(response)
            
            if decision.get('search_needed') and decision.get('query'):
                return True, decision.get('query'), decision.get('reason')
            else:
                return False, None, decision.get('reason', 'llm_decided_no_or_null_query')
                
        except Exception as e:
            logger.error(f" Active Search Error: {e}")
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

    def _build_thinking_prompt(self, message: str, context: str, previous_results: Optional[str] = None) -> str:
        base_prompt = f"""You are the internal monologue of an AI. Decide if you need to search your long-term memory to answer the user.

CONTEXT:
{context}

USER MESSAGE: "{message}"
"""

        if previous_results:
            base_prompt += f"""
PREVIOUS SEARCH RESULTS:
{previous_results}

TASK (REFINEMENT):
1. Did the PREVIOUS SEARCH RESULTS answer the user's specific question?
2. If YES, set "search_needed": false.
3. If NO, generate a NEW, DIFFERENT query to find the missing info.
"""
        else:
            base_prompt += f"""
TASK:
1. Do you have enough info in the CONTEXT to answer?
2. Is the user asking about a past event, fact, or conversation not shown here?
3. If YES to #2, generate a specific search query.
"""

        base_prompt += """
OUTPUT FORMAT (JSON ONLY):
{
    "search_needed": true/false,
    "query": "specific search terms" (REQUIRED if search_needed is true, otherwise null),
    "reason": "short explanation"
}

RESPONSE:
{"""
        return base_prompt

    def _parse_decision(self, response: str) -> Dict:
        """Parse the LLM response into a dict"""
        try:
            # Try to find JSON object using regex
            # Look for the last JSON object in the text (in case there are examples in the thinking)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
            
            # Fallback: Try to parse the whole thing if regex failed (unlikely but safe)
            cleaned = response.strip()
            if not cleaned.endswith('}'):
                cleaned += '}'
            if not cleaned.startswith('{'):
                cleaned = '{' + cleaned
                
            return json.loads(cleaned)
            
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f" Failed to parse thinking response: {response[:200]}...")
            # Fallback: simple text search if it looks like a query
            if len(response) < 50 and " " in response:
                 return {"search_needed": True, "query": response, "reason": "parsing_fallback"}
            return {"search_needed": False}
