"""Message perception — evidence detection, board parsing, personality analysis."""
import re
from typing import List, Dict, Optional
from serin.config.logger import logger


    def _detect_evidence(self, content: str) -> bool:
        """Detect if content contains factual evidence (boards, links, code, quotes)."""
        for pattern in self._EVIDENCE_PATTERNS:
            if re.search(pattern, content):
                return True
        return False

    def _perceive_message(self, content: str, user_id: str, username: str) -> PerceptionResult:
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
        if any(m in content_lower for m in _JOKE_MARKERS):
            result.speech_act = 'joke'
            result.is_objective = False

        # Sarcasm?
        if any(m in content_lower for m in _SARCASM_MARKERS):
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
        if self._detect_evidence(content):
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
        for pattern, category in _CLAIM_PATTERNS:
            match = re.search(pattern, content_lower)
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
                derived = self._derive_from_board(block['content'])
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

    def _parse_board(self, board_text: str) -> Optional[list[list[str]]]:
        """Parse a pipe-delimited board into a 2D grid.

        Handles:
          Connect 4: 6 rows × 7 cols, |X|O| | | | | |
          Tic-tac-toe: 3 rows × 3 cols, |X|O|X| or |X|O|X|
        Returns None if not parseable.
        """
        lines = [l.strip() for l in board_text.split('\n') if l.strip()]
        if not lines:
            return None

        grid = []
        for line in lines:
            # Strip leading/trailing pipes, split on |
            cells = [c.strip() for c in line.strip('|').split('|')]
            if not cells:
                continue
            grid.append(cells)

        if len(grid) < 2:
            return None

        # Validate: all rows same width
        widths = set(len(r) for r in grid)
        if len(widths) > 1:
            return None

        return grid

    def _derive_from_board(self, board_text: str) -> list[Dict]:
        """Derive game-level facts from a parsed board state.

        Applies known game rules:
          - Connect 4: 4 in a row → win condition met
          - Tic-tac-toe: 3 in a row → win condition met
        Returns list of derived facts with confidence and category.
        """
        grid = self._parse_board(board_text)
        if not grid:
            return []

        derived = []
        rows, cols = len(grid), len(grid[0])

        # Detect game type
        is_connect4 = rows == 6 and cols == 7
        is_tictactoe = rows == 3 and cols == 3
        win_length = 4 if is_connect4 else (3 if is_tictactoe else 0)

        if win_length == 0:
            # Generic board: still store it, but can't derive much
            derived.append({
                'content': f"A {rows}×{cols} board was shown",
                'category': 'board_state',
                'confidence': 0.9,
                'source_type': 'derived',
            })
            return derived

        # Check for pieces
        piece_positions = {'.': [], '_': []}
        for r in range(rows):
            for c in range(cols):
                cell = grid[r][c]
                if cell and cell not in ('.', '_', '', ' '):
                    if cell not in piece_positions:
                        piece_positions[cell] = []
                    piece_positions[cell].append((r, c))

        # Check for wins in all directions
        for piece, positions in piece_positions.items():
            pos_set = set(positions)

            # Check horizontal
            for r in range(rows):
                for c in range(cols - win_length + 1):
                    if all((r, c + i) in pos_set for i in range(win_length)):
                        derived.append({
                            'content': f"{piece} has {win_length} in a row horizontally at row {r+1} (columns {c+1}-{c+win_length})",
                            'category': 'game_result',
                            'confidence': 0.95,
                            'source_type': 'derived',
                        })

            # Check vertical
            for r in range(rows - win_length + 1):
                for c in range(cols):
                    if all((r + i, c) in pos_set for i in range(win_length)):
                        derived.append({
                            'content': f"{piece} has {win_length} in a row vertically at column {c+1} (rows {r+1}-{r+win_length})",
                            'category': 'game_result',
                            'confidence': 0.95,
                            'source_type': 'derived',
                        })

            # Check diagonal (down-right)
            for r in range(rows - win_length + 1):
                for c in range(cols - win_length + 1):
                    if all((r + i, c + i) in pos_set for i in range(win_length)):
                        derived.append({
                            'content': f"{piece} has {win_length} in a row diagonally (down-right) from ({r+1},{c+1})",
                            'category': 'game_result',
                            'confidence': 0.95,
                            'source_type': 'derived',
                        })

            # Check diagonal (down-left)
            for r in range(rows - win_length + 1):
                for c in range(win_length - 1, cols):
                    if all((r + i, c - i) in pos_set for i in range(win_length)):
                        derived.append({
                            'content': f"{piece} has {win_length} in a row diagonally (down-left) from ({r+1},{c+1})",
                            'category': 'game_result',
                            'confidence': 0.95,
                            'source_type': 'derived',
                        })

        if not derived:
            derived.append({
                'content': f"Board state captured ({rows}×{cols}) — no win condition detected yet",
                'category': 'board_state',
                'confidence': 0.7,
                'source_type': 'derived',
            })

        return derived

    def _analyze_personality(self, user_id: str, content: str) -> list[str]:
        """Analyze message and update personality traits. Returns detected traits."""
        traits = []
        interests = []
        content_lower = content.lower()

        if any(w in content_lower for w in [            "lol", "haha", "lmao"]):
            traits.append("humorous")
        if any(w in content_lower for w in ["thanks", "please", "sorry"]):
            traits.append("polite")
        if len(content) > 200:
            traits.append("verbose")
        elif len(content) < 20:
            traits.append("concise")
        if content.count("!") > 2:
            traits.append("enthusiastic")

        interest_keywords = {
            "gaming": ["game", "play", "steam", "xbox", "ps5"],
            "anime": ["anime", "manga", "weeb"],
            "music": ["song", "music", "band", "album"],
            "tech": ["code", "programming", "ai", "computer"],
            "art": ["draw", "art", "paint", "sketch"],
        }
        for interest, keywords in interest_keywords.items():
            if any(kw in content_lower for kw in keywords):
                interests.append(interest)

        if traits or interests:
            self.memory.update_user_traits(user_id, traits, interests)

        return traits

    def _get_emotional_tone(self, sentiment_score: float) -> str:
        """Convert sentiment score to emotional tone"""
        if sentiment_score > 0.5:
            return "happy"
        elif sentiment_score > 0.2:
            return "positive"
        elif sentiment_score < -0.5:
            return "sad"
        elif sentiment_score < -0.2:
            return "negative"
        return "neutral"

    def _detect_topic(self, content: str) -> Optional[str]:
        """Simple topic detection"""
        content_lower = content.lower()
        topics = {
            "gaming": ["game", "gaming", "play", "steam", "xbox", "ps5", "nintendo"],
            "anime": ["anime", "manga", "weeb"],
            "music": ["song", "music", "band", "album", "spotify"],
            "food": ["food", "eat", "cooking", "recipe", "restaurant"],
            "work": ["work", "job", "boss", "office", "meeting"],
            "school": ["school", "class", "homework", "exam", "teacher"],
            "movies": ["movie", "film", "cinema", "netflix"],
            "sports": ["sport", "football", "basketball", "soccer", "gym"],
        }
        for topic, keywords in topics.items():
            if any(kw in content_lower for kw in keywords):
                return topic
        return None

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile"""
        return self.memory.get_user_profile(user_id)

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        stats = self.memory.get_stats()
        stats["manager_stats"] = self.stats
        stats["enhanced_context"] = {
            "improvements_used": self.stats["context_improvements"],
            "current_source": "enhanced",
        }
        if hasattr(self.memory, "qdrant_client"):
            stats["memory_system"] = "Qdrant"
            stats["memory_features"] = {
                "hybrid_search": True,
                "bm25_available": hasattr(self.memory, "bm25_index"),
                "embedding_available": hasattr(self.memory, "embedding_model"),
            }
        return stats


# Alias for backward compatibility with discord_bot.py
MessageManagerV3 = EnhancedMessageManagerV3
