"""Evidence detection and message perception (classification + extraction)."""

from __future__ import annotations

import json
import re
from typing import Any

from serin.d1_4_config_base.d2_3_logger import logger

from .d5_1_perception_board import derive_from_board
from .d5_5_perception_result import (
    CLAIM_PATTERNS,
    JOKE_MARKERS,
    SARCASM_MARKERS,
    PerceptionResult,
)

EVIDENCE_PATTERNS = [
    r'\|.*\|.*\|',        # Board states (pipes with separators)
    r'https?://\S+',       # URLs
    r'```[\s\S]*?```',     # Code blocks
    r'"[^"]{20,}"',        # Long quotes (20+ chars)
]


def detect_evidence(self: Any, content: str) -> bool:
    """Detect if content contains factual evidence (boards, links, code, quotes)."""
    for pattern in EVIDENCE_PATTERNS:
        if re.search(pattern, content):
            return True
    return False


def _analyze_speech_act(content: str, content_lower: str, result: PerceptionResult) -> None:
    if content.strip().endswith('?'):
        result.speech_act = 'question'
        result.is_objective = True
    if any(m in content_lower for m in JOKE_MARKERS):
        result.speech_act = 'joke'
        result.is_objective = False
    if any(m in content_lower for m in SARCASM_MARKERS):
        result.speech_act = 'sarcasm'
        result.is_objective = False
    if re.search(r'^(yeah|yes|right|true|agreed|exactly|correct)\b', content_lower):
        result.speech_act = 'agreement'
    if re.search(r'^(no|nah|nope|wrong|nah)\b', content_lower) or \
       re.search(r'\b(?:actually|but)\s+(?:no|that\'?s?\s+wrong|you\'?re?\s+wrong)\b', content_lower):
        result.speech_act = 'disagreement'
    if detect_evidence(None, content):
        result.speech_act = 'evidence'
        result.is_objective = True
    if re.search(r'^(?:tell|show|explain|describe|list|give|do|say)\b', content_lower):
        result.speech_act = 'instruction'


def _extract_evidence(content: str, result: PerceptionResult) -> None:
    board_match = re.search(r'(\|.*?\|.*?\|[^\n]*(\n\|.*?\|.*?\|[^\n]*)*)', content, re.DOTALL)
    if board_match:
        result.evidence_blocks.append({
            'type': 'board', 'content': board_match.group(1).strip(),
            'evidence_class': 'world', 'metadata': {},
        })
    for url in re.findall(r'https?://\S+', content):
        result.evidence_blocks.append({
            'type': 'url', 'content': url, 'evidence_class': 'world', 'metadata': {},
        })
    code_match = re.search(r'```(\w*)\n([\s\S]*?)```', content)
    if code_match:
        result.evidence_blocks.append({
            'type': 'code', 'content': code_match.group(2).strip(),
            'evidence_class': 'world', 'metadata': {'language': code_match.group(1)},
        })
    for quote in re.findall(r'"([^"]{20,})"', content):
        result.evidence_blocks.append({
            'type': 'quote', 'content': quote, 'evidence_class': 'world', 'metadata': {},
        })


def _detect_claims(content: str, content_lower: str, result: PerceptionResult, username: str, user_id: str) -> None:
    claimant = username or user_id
    for pattern, category in CLAIM_PATTERNS:
        match = re.search(pattern, content)
        if match:
            result.claims.append({'claimant': claimant, 'content': match.group(0), 'category': category})
    for assertion in re.findall(r'\bI\s+(?:am|was|have|think|believe|feel|know|can|could|will|would)\s+(.+?)(?:\.|,|$)', content):
        result.claims.append({'claimant': claimant, 'content': f"I {assertion.strip()}", 'category': 'self_statement'})
    for assertion in re.findall(r'\byou\'(?:re|ve|are|were)\s+(.+?)(?:\.|,|$)', content_lower):
        result.claims.append({'claimant': claimant, 'content': f"you're {assertion.strip()}", 'category': 'other_directed'})


def _extract_observations(result: PerceptionResult) -> None:
    for block in result.evidence_blocks:
        if block['type'] == 'board':
            result.observations.append(f"The board shows: {block['content']}")
            result.extracted_facts.append({
                'content': f"The board shows: {block['content']}",
                'category': 'board_state', 'confidence': 0.9, 'source_type': 'evidence_extracted',
            })
        elif block['type'] == 'url':
            result.observations.append(f"A reference was shared: {block['content']}")
            result.extracted_facts.append({
                'content': f"A reference was linked: {block['content']}",
                'category': 'reference', 'confidence': 0.7, 'source_type': 'evidence_extracted',
            })
        elif block['type'] == 'code':
            result.observations.append(f"Code was shared: {block['content'][:100]}")
            result.extracted_facts.append({
                'content': f"Code shown: {block['content'][:200]}",
                'category': 'code', 'confidence': 0.8, 'source_type': 'evidence_extracted',
            })
    for claim in result.claims:
        result.observations.append(f"{claim['claimant']} claims: {claim['content']}")
        if claim['category'] in ('win_claim', 'loss_attribution', 'self_assessment'):
            result.extracted_facts.append({
                'content': f"{claim['claimant']} claimed: {claim['content']}",
                'category': 'speech_claim', 'confidence': 0.2, 'source_type': 'user_claim',
            })


def _derive_facts_from_boards(result: PerceptionResult, self_obj: Any) -> None:
    for block in result.evidence_blocks:
        if block['type'] == 'board':
            derived = derive_from_board(self_obj, block['content'])
            for fact in derived:
                result.extracted_facts.append(fact)
                result.observations.append(f"Derived: {fact['content']}")


def _determine_evidence_class(result: PerceptionResult, self_obj: Any, content: str) -> None:
    if result.evidence_blocks:
        result.evidence_class = 'world'
    elif result.claims:
        result.evidence_class = 'conversation'
    else:
        sentiment_score: float = 0.0
        if hasattr(self_obj, '_analyzer') and self_obj._analyzer is not None:
            try:
                sentiment_score = self_obj._analyzer.polarity_scores(content).get("compound", 0.0)
            except Exception:
                sentiment_score = 0.0
        if abs(sentiment_score) > 0.7:
            result.evidence_class = 'social'


def _classify_intent(content_lower: str, result: PerceptionResult) -> None:
    if result.speech_act == 'question':
        result.intent = 'question'
    elif any(m in content_lower for m in ['why', 'how', 'explain', 'what']):
        result.intent = 'seek_explanation'
    elif any(m in content_lower for m in ['am i right', 'did i', 'check', 'rate']):
        result.intent = 'seek_validation'
    elif result.speech_act == 'joke':
        result.intent = 'seek_joke'
    elif result.speech_act == 'disagreement':
        result.intent = 'seek_argument'
    elif result.speech_act == 'instruction':
        result.intent = 'command'
    elif result.speech_act in ('agreement', 'statement'):
        result.intent = 'social'


def perceive_message(self: Any, content: str, user_id: str, username: str) -> PerceptionResult:
    """Analyze message before storage — classify, extract evidence, claims, facts."""
    logger.info("PERCEIVE CALLED: content=%s user=%s", content[:80], username)
    content_lower = content.lower()
    result = PerceptionResult(speech_act='statement', is_objective=False)

    _analyze_speech_act(content, content_lower, result)
    _extract_evidence(content, result)
    _detect_claims(content, content_lower, result, username, user_id)
    _extract_observations(result)
    _derive_facts_from_boards(result, self)
    _determine_evidence_class(result, self, content)
    _classify_intent(content_lower, result)

    if result.evidence_blocks:
        result.is_objective = True
    elif result.claims:
        result.is_objective = False

    logger.info("FACTS EXTRACTED: %d facts from '%s'", len(result.extracted_facts), content[:60])
    return result


async def extract_facts_from_message(
    content: str,
    username: str,
    user_id: str,
    llm_connector: Any,
) -> list[dict[str, Any]]:
    """Inline LLM-based fact extraction. Uses SMALL/FAST model, not the main model.

    Replaces regex-based conversational pattern matching with LLM extraction.
    """
    if not content or len(content.strip()) < 5:
        return []

    prompt = f"""Extract factual claims from this Discord message.
Message from {username}: "{content}"

Return a JSON array. Each item:
{{"subject_username": "who it's about",
  "claim": "the fact in simple words",
  "category": "preference|identity|profession|location|event|opinion|relationship",
  "confidence": 0.0-1.0,
  "source_type": "self|other|reported|inferred"}}

Rules:
- "I love pizza" → subject: "{username}", source_type: "self", confidence: 0.75
- "Rin loves chicken" → subject: "Rin", source_type: "other", confidence: 0.45
- "Rin said he loves chicken" → subject: "Rin", source_type: "reported", confidence: 0.35
- "I hate Mondays" → confidence: 0.75
- Questions/greetings/reactions/small talk → return empty array []
- Be conservative. If in doubt, don't extract.

Return ONLY a valid JSON array. No markdown. No explanation."""

    try:
        response = await llm_connector.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        text = re.sub(r'^```(?:json)?\s*', '', response.strip())
        text = re.sub(r'\s*```$', '', text)
        facts: Any = json.loads(text)
        return facts if isinstance(facts, list) else []
    except Exception as e:
        logger.exception("LLM fact extraction failed: %s", e)
        return []


async def detect_contradictions(
    content: str,
    username: str,
    user_id: str,
    memory_system: Any,
    llm_connector: Any,
) -> list[int]:
    """Detect if this message contradicts known facts about the user.

    Uses the SMALL/FAST model. Returns list of fact_ids that are contradicted.
    """
    from serin.d1_3_state_core.d2_2_core_memory.d3_3_belief_dynamics import (
        BayesianBeliefEngine,
    )
    engine: BayesianBeliefEngine | None = getattr(memory_system, "belief_engine", None)
    if engine is None:
        return []

    facts = engine.get_facts_for_user(user_id, limit=10)
    if not facts:
        return []

    fact_list = "\n".join(
        f"{i+1}. {f['claim']} (confidence: {f['belief']:.2f})"
        for i, f in enumerate(facts)
    )

    prompt = f"""Does this message from {username} CONTRADICT any of these
known facts about them?

Message: "{content}"

Known facts:
{fact_list}

Reply with a JSON array of fact NUMBERS (1-indexed) that are
directly contradicted. If no contradiction, return empty array [].
Be strict — only flag genuine contradictions, not updates or
elaborations. Example:
- Known: "loves pizza", Message: "I hate pizza" → [1]
- Known: "lives in Tokyo", Message: "I moved to Osaka" → [1]
- Known: "loves pizza", Message: "I had sushi today" → []

Reply ONLY with JSON array. No explanation."""

    try:
        response = await llm_connector.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
        )
        text = re.sub(r'[^\[\d,\s\-\]]', '', response.strip())
        nums: Any = json.loads(text)
        if not isinstance(nums, list):
            return []
        result_ids: list[int] = []
        for n in nums:
            if isinstance(n, int) and 1 <= n <= len(facts):
                result_ids.append(facts[n - 1]["_fact_id"])
        return result_ids
    except Exception as e:
        logger.exception("Contradiction detection failed: %s", e)
        return []
