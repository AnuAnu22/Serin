"""Perception result types and message-classification patterns."""

from dataclasses import dataclass, field
from typing import Any

# ── Perception patterns ──────────────────────────────────────────────────────

# Claim patterns: subjective assertions about self, others, or how things are
CLAIM_PATTERNS = [
    (r'\bI\s+won\b', 'win_claim'),
    (r'\byou\s+lost\b', 'loss_attribution'),
    (r'\bI\'\w+\s+(?:right|correct|wrong|better|best)\b', 'self_assessment'),
    (r'\byou\s+\'\w+\s+(?:wrong|incorrect|mistaken)\b', 'other_correction'),
    (r'\b(?:actually|honestly|truthfully|literally)\s*,?\s+(?:\w+)', 'emphasis_claim'),
]

# Sarcasm indicators
SARCASM_MARKERS = [
    'oh sure', 'yeah right', 'obviously', 'clearly',
    'as i', 'sure thing', 'totally', 'no way',
    'big brain', 'galaxy brain',
]

# Joke indicators
JOKE_MARKERS = ['lol', 'lmao', 'rofl', 'jk', 'kidding', 'just joking', 'haha', 'hehe', 'xd']

# Argument keywords (for mood-based filtering at retrieval time)
ARGUMENT_KEYWORDS = ['lose', 'lost', 'win', 'won', 'admit', 'wrong',
                     'cope', 'argue', 'disagree', 'disagreed', 'prove']


@dataclass
class PerceptionResult:
    """Structured analysis of an incoming message before storage.

    Transforms a raw text string into classified information that the
    memory system can store with proper provenance. Separates:
      - What was *said* (the speech act)
      - What *evidence* was presented (boards, URLs, code, quotes)
      - What *claims* were made (subjective assertions)
      - What *observations* can be extracted (verifiable content)
    """
    speech_act: str  # assertion | question | joke | sarcasm | agreement | disagreement | evidence | statement | instruction
    is_objective: bool  # primarily factual/verifiable?
    evidence_class: str = 'conversation'  # world | conversation | social | system
    intent: str = 'statement'  # seek_validation | seek_explanation | seek_argument | seek_joke | social | question | command | statement
    evidence_blocks: list[dict[str, Any]] = field(default_factory=lambda: [])  # [{type, content, metadata, evidence_class}]
    claims: list[dict[str, Any]] = field(default_factory=lambda: [])  # [{claimant, content, category}]
    observations: list[str] = field(default_factory=lambda: [])  # verifiable observations extracted
    extracted_facts: list[dict[str, Any]] = field(default_factory=lambda: [])  # [{content, category, confidence, source_type}]
