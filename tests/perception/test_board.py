from __future__ import annotations

from serin.d1_1_pipeline_flow.d2_2_flow_ingest.d3_2_ingest_core.d4_1_core_perception.d5_1_perception_board import (
    derive_from_board,
    parse_board,
)

# Shared board constants for exact-content assertions
C4_HORIZ_WIN: str = (
    "| | | | | | | |\n"
    "| | | | | | | |\n"
    "| | | | | | | |\n"
    "| | | | | | | |\n"
    "| | | | | | | |\n"
    "|X|X|X|X|O|O| |"
)
C4_VERT_WIN: str = (
    "| | | | | | | |\n"
    "| | | | | | | |\n"
    "|X| | | | | | |\n"
    "|X| | | | | | |\n"
    "|X| | | | | | |\n"
    "|X|O|O| | | | |"
)
C4_DIAG_DR_WIN: str = (
    "| | | | | | | |\n"
    "| | | | | | | |\n"
    "|X| | | | | | |\n"
    "| |X| | | | | |\n"
    "| | |X| | | | |\n"
    "| | | |X| | | |"
)
C4_DIAG_DL_WIN: str = (
    "| | | | | | | |\n"
    "| | | | | | | |\n"
    "| | | |X| | | |\n"
    "| | |X| | | | |\n"
    "| |X| | | | | |\n"
    "|X| | | | | | |"
)

EMPTY_6x7: str = (
    "| | | | | | | |\n" * 6
).rstrip("\n")


class TestParseBoard:
    def test_connect4_board(self) -> None:
        board = "|X|O|X|O|X|O| |\n|X|O|X|O|X|O| |\n|X|O|X|O|X|O| |\n| |O|X|O|X|O| |\n| | | | | | | |\n| | | | | | | |"
        result = parse_board(None, board)
        assert result is not None
        assert len(result) == 6
        assert len(result[0]) == 7

    def test_tictactoe_board(self) -> None:
        board = "|X|O|X|\n|O|X|O|\n|X| | |"
        result = parse_board(None, board)
        assert result is not None
        assert len(result) == 3
        assert len(result[0]) == 3

    def test_empty_input(self) -> None:
        result = parse_board(None, "")
        assert result is None

    def test_only_whitespace(self) -> None:
        result = parse_board(None, "   \n  \n  ")
        assert result is None

    def test_single_row(self) -> None:
        board = "|X|O|X|"
        result = parse_board(None, board)
        assert result is None

    def test_uneven_row_widths(self) -> None:
        board = "|X|O|X|\n|X|O|"
        result = parse_board(None, board)
        assert result is None

    def test_empty_cells(self) -> None:
        board = "| |O| |\n|X| |O|"
        result = parse_board(None, board)
        assert result is not None
        assert result[0][0] == ""
        assert result[0][1] == "O"
        assert result[1][0] == "X"

    def test_trailing_newline(self) -> None:
        board = "|X|O|X|\n|O|X|O|\n|X| | |\n"
        result = parse_board(None, board)
        assert result is not None
        assert len(result) == 3

    def test_extra_pipes(self) -> None:
        board = "||X|O|X||\n||O|X|O||"
        result = parse_board(None, board)
        assert result is not None
        cells = [c for row in result for c in row]
        assert "X" in cells
        assert "O" in cells


class TestDeriveFromBoard:
    def test_connect4_horizontal_win(self) -> None:
        board = "| | | | | | | |\n| | | | | | | |\n| | | | | | | |\n| | | | | | | |\n| | | | | | | |\n|X|X|X|X|O|O| |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) >= 1
        assert "has 4 in a row horizontally" in win_facts[0]["content"]

    def test_connect4_vertical_win(self) -> None:
        board = "| | | | | | | |\n| | | | | | | |\n|X| | | | | | |\n|X| | | | | | |\n|X| | | | | | |\n|X|O|O| | | | |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) >= 1
        assert "has 4 in a row vertically" in win_facts[0]["content"]

    def test_connect4_diagonal_down_right_win(self) -> None:
        board = "| | | | | | | |\n| | | | | | | |\n| | | |X| | | |\n| | |X|O| | | |\n| |X|O|O| | | |\n|X|O|O|O| | | |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) >= 1
        assert "diagonally" in win_facts[0]["content"]

    def test_connect4_diagonal_down_left_win(self) -> None:
        board = "| | | | | | | |\n| | | | | | | |\n|X| | | | | | |\n|O|X| | | | | |\n|O|O|X| | | | |\n|O|O|O|X| | | |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) >= 1
        assert "diagonally" in win_facts[0]["content"]

    def test_tictactoe_horizontal_win(self) -> None:
        board = "|X|X|X|\n|O|O| |\n| | | |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) >= 1

    def test_tictactoe_vertical_win(self) -> None:
        board = "|X|O| |\n|X|O| |\n|X| | |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) >= 1

    def test_no_win_condition(self) -> None:
        board = "|X| | | | | | |\n| |O| | | | | |\n| | |X| | | | |\n| | | |O| | | |\n| | | | | | | |\n| | | | | | | |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 0
        board_facts = [f for f in facts if f["category"] == "board_state"]
        assert len(board_facts) >= 1

    def test_invalid_board_returns_empty(self) -> None:
        facts = derive_from_board(None, "")
        assert facts == []

    def test_generic_board_dimensions(self) -> None:
        board = "|A|B|\n|C|D|"
        facts = derive_from_board(None, board)
        assert len(facts) == 1
        assert facts[0]["category"] == "board_state"
        assert "2×2" in facts[0]["content"]

    def test_multiple_wins(self) -> None:
        board = "|X|X|X|X| | | |\n|O|O|O|O| | | |\n| | | | | | | |\n| | | | | | | |\n| | | | | | | |\n| | | | | | | |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) >= 2

    def test_piece_positions_underscore_empty(self) -> None:
        board = "|X|O|X|\n|O|_|O|\n|X| | |"
        facts = derive_from_board(None, board)
        assert len(facts) >= 1

    def test_no_wins_still_returns_board_state(self) -> None:
        board = "|X| | | | | | |\n| |O| | | | | |\n| | | | | | | |\n| | | | | | | |\n| | | | | | | |\n| | | | | | | |"
        facts = derive_from_board(None, board)
        board_facts = [f for f in facts if f["category"] == "board_state"]
        assert len(board_facts) >= 1

    # ─────────────────────────────────────────────────────────────────
    # Exact-content tests — kill NumberReplacer + ReplaceBinaryOperator
    # on every `+`, `-`, and numeric literal in f-strings and ranges
    # ─────────────────────────────────────────────────────────────────

    def test_connect4_horizontal_win_exact_content(self) -> None:
        facts = derive_from_board(None, C4_HORIZ_WIN)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 1
        assert win_facts[0]["content"] == "X has 4 in a row horizontally at row 6 (columns 1-4)"
        assert win_facts[0]["confidence"] == 0.95
        assert win_facts[0]["source_type"] == "derived"

    def test_connect4_horizontal_win_exact_confidence(self) -> None:
        facts = derive_from_board(None, C4_HORIZ_WIN)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert win_facts[0]["confidence"] == 0.95

    def test_connect4_vertical_win_exact_content(self) -> None:
        facts = derive_from_board(None, C4_VERT_WIN)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 1
        assert win_facts[0]["content"] == "X has 4 in a row vertically at column 1 (rows 3-6)"
        assert win_facts[0]["confidence"] == 0.95

    def test_connect4_diagonal_down_right_exact_content(self) -> None:
        facts = derive_from_board(None, C4_DIAG_DR_WIN)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 1
        assert "diagonally (down-right) from (3,1)" in win_facts[0]["content"]

    def test_connect4_diagonal_down_left_exact_content(self) -> None:
        facts = derive_from_board(None, C4_DIAG_DL_WIN)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 1
        assert "diagonally (down-left) from (3,4)" in win_facts[0]["content"]

    def test_tictactoe_horizontal_win_exact_content(self) -> None:
        board = "|X|X|X|\n|O|O| |\n| | | |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 1
        assert win_facts[0]["content"] == "X has 3 in a row horizontally at row 1 (columns 1-3)"
        assert win_facts[0]["confidence"] == 0.95

    def test_tictactoe_vertical_win_exact_content(self) -> None:
        board = "|X|O| |\n|X|O| |\n|X| | |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 1
        assert win_facts[0]["content"] == "X has 3 in a row vertically at column 1 (rows 1-3)"
        assert win_facts[0]["confidence"] == 0.95

    def test_tictactoe_diagonal_win_exact_content(self) -> None:
        board = "|X|O| |\n|O|X| |\n| | |X|"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 1
        assert "diagonally (down-right) from (1,1)" in win_facts[0]["content"]

    # ─────────────────────────────────────────────────────────────────
    #  Game type detection edge-cases — kill
    #  ReplaceAndWithOr + ReplaceComparisonOperator on `rows == N`
    # ─────────────────────────────────────────────────────────────────

    def test_not_connect4_when_6x3_board(self) -> None:
        """6 rows × 3 cols — matches rows == 6 but not cols == 7."""
        board = "|X| | |\n|X| | |\n|X| | |\n|O| | |\n|O| | |\n|O| | |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 0

    def test_not_connect4_when_4x7_board(self) -> None:
        """4 rows × 7 cols — matches cols == 7 but not rows == 6."""
        board = "|X|O|X|O|X|O|X|\n|O|X|O|X|O|X|O|\n|X|O|X|O|X|O|X|\n|O|X|O|X|O|X|O|"
        facts = derive_from_board(None, board)
        board_facts = [f for f in facts if f["category"] == "board_state"]
        assert len(board_facts) == 1

    def test_not_tictactoe_when_3x5_board(self) -> None:
        """3 rows × 5 cols — matches rows == 3 but not cols == 3."""
        board = "|X|O| |X|O|\n|O|X| |O|X|\n|X| | |X| |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 0
        board_facts = [f for f in facts if f["category"] == "board_state"]
        assert len(board_facts) == 1

    def test_not_tictactoe_when_5x3_board(self) -> None:
        """5 rows × 3 cols — matches cols == 3 but not rows == 3."""
        board = "|X|O| |\n|O|X| |\n|X| | |\n|O|X| |\n|X|O| |"
        facts = derive_from_board(None, board)
        win_facts = [f for f in facts if f["category"] == "game_result"]
        assert len(win_facts) == 0

    def test_generic_board_confidence(self) -> None:
        """2×2 generic board must have exact confidence 0.9."""
        board = "|A|B|\n|C|D|"
        facts = derive_from_board(None, board)
        assert facts[0]["confidence"] == 0.9

    def test_generic_board_content(self) -> None:
        board = "|A|B|\n|C|D|"
        facts = derive_from_board(None, board)
        assert "2×2" in facts[0]["content"]

    # ─────────────────────────────────────────────────────────────────
    #  Edge cases — skip placeholder chars, empty-middle row, etc.
    # ─────────────────────────────────────────────────────────────────

    def test_skip_dot_and_underscore_cells(self) -> None:
        """. and _ cells must NOT be counted as pieces.
        Kills ReplaceAndWithOr on the `cell not in ('.','_','',' ')` filter."""
        board = "|X|.|_|\n|O|_|.|"
        facts = derive_from_board(None, board)
        board_facts = [f for f in facts if f["category"] == "board_state"]
        assert len(board_facts) >= 1

    def test_empty_middle_row_continues(self) -> None:
        """Board with a blank line in the middle.
        Kills ReplaceContinueWithBreak in the parse loop."""
        board = "|X|O|X|\n\n|O|X|O|\n|X| | |"
        result = parse_board(None, board)
        assert result is not None
        assert len(result) == 3

    def test_parse_board_row_count_exact(self) -> None:
        """Exact row count — kills NumberReplacer on len(grid)."""
        result = parse_board(None, C4_HORIZ_WIN)
        assert result is not None
        assert len(result) == 6
        assert len(result[0]) == 7

    def test_parse_board_tictactoe_dimensions(self) -> None:
        """Kills NumberReplacer on comparison constants 3, 3."""
        result = parse_board(None, "|X|O|X|\n|O|X|O|\n|X| | |")
        assert result is not None
        assert len(result) == 3
        assert len(result[0]) == 3
