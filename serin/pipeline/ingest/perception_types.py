"""PerceptionResult and message classification patterns."""
from dataclasses import dataclass, field
from typing import List, Dict


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
    evidence_blocks: List[Dict] = field(default_factory=list)  # [{type, content, metadata, evidence_class}]
    claims: List[Dict] = field(default_factory=list)  # [{claimant, content, category}]
    observations: List[str] = field(default_factory=list)  # verifiable observations extracted
    extracted_facts: List[Dict] = field(default_factory=list)  # [{content, category, confidence, source_type}]


# ── Perception patterns ──────────────────────────────────────────────────────

# Claim patterns: subjective assertions about self, others, or how things are
_CLAIM_PATTERNS = [
    (r'\bI\s+won\b', 'win_claim'),
    (r'\byou\s+lost\b', 'loss_attribution'),
    (r'\bI\'\w+\s+(?:right|correct|wrong|better|best)\b', 'self_assessment'),
    (r'\byou\s+\'\w+\s+(?:wrong|incorrect|mistaken)\b', 'other_correction'),
    (r'\b(?:actually|honestly|truthfully|literally)\s*,?\s+(?:\w+)', 'emphasis_claim'),
]

# Sarcasm indicators
_SARCASM_MARKERS = [
    'oh sure', 'yeah right', 'obviously', 'clearly',
    'as if', 'sure thing', 'totally', 'no way',
    'big brain', 'galaxy brain',
]

# Joke indicators  
_JOKE_MARKERS = ['lol', 'lmao', 'rofl', 'jk', 'kidding', 'just joking', 'haha', 'hehe', 'xd']

# Argument keywords (for mood-based filtering at retrieval time)
_ARGUMENT_KEYWORDS = ['lose', 'lost', 'win', 'won', 'admit', 'wrong',
                       'cope', 'argue', 'disagree', 'disagreed', 'prove']



