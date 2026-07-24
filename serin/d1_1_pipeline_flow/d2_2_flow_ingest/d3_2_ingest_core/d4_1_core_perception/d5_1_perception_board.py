"""Board parsing and game-fact derivation from pipe-delimited board states."""

from __future__ import annotations

from typing import Any


def parse_board(self: Any, board_text: str) -> list[list[str]] | None:
    """Parse a pipe-delimited board into a 2D grid.

    Handles:
      Connect 4: 6 rows × 7 cols, |X|O| | | | | |
      Tic-tac-toe: 3 rows × 3 cols, |X|O|X| or |X|O|X|
    Returns None if not parseable.
    """
    lines = [line.strip() for line in board_text.split('\n') if line.strip()]
    if not lines:
        return None

    grid: list[list[str]] = []
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


def derive_from_board(self: Any, board_text: str) -> list[dict[str, Any]]:
    """Derive game-level facts from a parsed board state.

    Applies known game rules:
      - Connect 4: 4 in a row → win condition met
      - Tic-tac-toe: 3 in a row → win condition met
    Returns list of derived facts with confidence and category.
    """
    grid = parse_board(self, board_text)
    if not grid:
        return []

    derived: list[dict[str, Any]] = []
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
    piece_positions: dict[str, list[tuple[int, int]]] = {'.': [], '_': []}
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
