"""Evidence detection and message perception (classification + extraction)."""

from __future__ import annotations

import re
from typing import Any

from .board import derive_from_board
from .result import (
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


def perceive_message(self: Any, content: str, user_id: str, username: str) -> PerceptionResult:
    """Analyze message before storage — classify, extract evidence, claims, facts.

    This is the perception layer. It transforms raw text into structured
    information so the memory system stores *what the message contains*
    rather than just *the text itself*.
    """
    content_lower = content.lower()
    result = PerceptionResult(speech_act='statement', is_objective=False)

    # ── 1. Classify speech act ────────────────────────────────────────
    # Question?
    if content.strip().endswith('?'):
        result.speech_act = 'question'
        result.is_objective = True  # Questions seek truth

    # Joke?
    if any(m in content_lower for m in JOKE_MARKERS):
        result.speech_act = 'joke'
        result.is_objective = False

    # Sarcasm?
    if any(m in content_lower for m in SARCASM_MARKERS):
        result.speech_act = 'sarcasm'
        result.is_objective = False

    # Agreement?
    if re.search(r'^(yeah|yes|right|true|agreed|exactly|correct)\b', content_lower):
        result.speech_act = 'agreement'

    # Disagreement?
    if re.search(r'^(no|nah|nope|wrong|nah)\b', content_lower) or \
       re.search(r'\b(?:actually|but)\s+(?:no|that\'?s?\s+wrong|you\'?re?\s+wrong)\b', content_lower):
        result.speech_act = 'disagreement'

    # Evidence?
    if detect_evidence(self, content):
        result.speech_act = 'evidence'
        result.is_objective = True

    # Instruction?
    if re.search(r'^(?:tell|show|explain|describe|list|give|do|say)\b', content_lower):
        result.speech_act = 'instruction'

    # ── 2. Extract evidence blocks with class ─────────────────────────
    # Board states: |...|...|...| across multiple lines
    board_match = re.search(r'(\|.*?\|.*?\|[^\n]*(\n\|.*?\|.*?\|[^\n]*)*)', content, re.DOTALL)
    if board_match:
        result.evidence_blocks.append({
            'type': 'board',
            'content': board_match.group(1).strip(),
            'evidence_class': 'world',
            'metadata': {},
        })

    # URLs
    url_matches = re.findall(r'https?://\S+', content)
    for url in url_matches:
        result.evidence_blocks.append({
            'type': 'url',
            'content': url,
            'evidence_class': 'world',
            'metadata': {},
        })

    # Code blocks
    code_match = re.search(r'```(\w*)\n([\s\S]*?)```', content)
    if code_match:
        result.evidence_blocks.append({
            'type': 'code',
            'content': code_match.group(2).strip(),
            'evidence_class': 'world',
            'metadata': {'language': code_match.group(1)},
        })

    # Long quotes
    quote_matches = re.findall(r'"([^"]{20,})"', content)
    for quote in quote_matches:
        result.evidence_blocks.append({
            'type': 'quote',
            'content': quote,
            'evidence_class': 'world',
            'metadata': {},
        })

    # ── 3. Extract claims (subjective assertions) ─────────────────────
    for pattern, category in CLAIM_PATTERNS:
        match = re.search(pattern, content)
        if match:
            result.claims.append({
                'claimant': username or user_id,
                'content': match.group(0),
                'category': category,
            })

    # General first-person assertions
    i_assertions = re.findall(r'\bI\s+(?:am|was|have|think|believe|feel|know|can|could|will|would)\s+(.+?)(?:\.|,|$)', content)
    for assertion in i_assertions:
        result.claims.append({
            'claimant': username or user_id,
            'content': f"I {assertion.strip()}",
            'category': 'self_statement',
        })

    # General third-person about bot
    you_assertions = re.findall(r'\byou\'(?:re|ve|are|were)\s+(.+?)(?:\.|,|$)', content_lower)
    for assertion in you_assertions:
        result.claims.append({
            'claimant': username or user_id,
            'content': f"you're {assertion.strip()}",
            'category': 'other_directed',
        })

    # ── 4. Extract observations (verifiable content) ──────────────────
    # Board states are always observations
    for block in result.evidence_blocks:
        if block['type'] == 'board':
            result.observations.append(
                f"The board shows: {block['content']}"
            )
            # Board states become high-confidence facts
            result.extracted_facts.append({
                'content': f"The board shows: {block['content']}",
                'category': 'board_state',
                'confidence': 0.9,
                'source_type': 'evidence_extracted',
            })
        elif block['type'] == 'url':
            result.observations.append(f"A reference was shared: {block['content']}")
            result.extracted_facts.append({
                'content': f"A reference was linked: {block['content']}",
                'category': 'reference',
                'confidence': 0.7,
                'source_type': 'evidence_extracted',
            })
        elif block['type'] == 'code':
            result.observations.append(f"Code was shared: {block['content'][:100]}")
            result.extracted_facts.append({
                'content': f"Code shown: {block['content'][:200]}",
                'category': 'code',
                'confidence': 0.8,
                'source_type': 'evidence_extracted',
            })

    # If the user is making claims about who won or lost, extract
    # the *claim* as an observation of speech (not a fact about the game)
    for claim in result.claims:
        result.observations.append(
            f"{claim['claimant']} claims: {claim['content']}"
        )
        # Claims become low-confidence facts — the *claim itself* is a fact
        # of speech, but the *content* is not verified
        if claim['category'] in ('win_claim', 'loss_attribution', 'self_assessment'):
            result.extracted_facts.append({
                'content': f"{claim['claimant']} claimed: {claim['content']}",
                'category': 'speech_claim',
                'confidence': 0.2,
                'source_type': 'user_claim',
            })

    # ── 5. Derive facts from evidence — board parsing + rule application ──
    for block in result.evidence_blocks:
        if block['type'] == 'board':
            derived = derive_from_board(self, block['content'])
            for fact in derived:
                result.extracted_facts.append(fact)
                result.observations.append(
                    f"Derived: {fact['content']}"
                )

    # ── 7. Determine evidence_class ──────────────────────────────────
    if result.evidence_blocks:
        result.evidence_class = 'world'
    elif result.claims:
        result.evidence_class = 'conversation'
    else:
        # Check for highly emotional content
        sentiment = self.analyzer.polarity_scores(content)
        if abs(sentiment['compound']) > 0.7:
            result.evidence_class = 'social'

    # ── 8. Determine intent ───────────────────────────────────────────
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

    # ── 9. Determine objectivity ──────────────────────────────────────
    if result.evidence_blocks:
        result.is_objective = True
    elif result.claims:
        result.is_objective = False

    return result
