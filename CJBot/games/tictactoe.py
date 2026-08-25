"""Tic-Tac-Toe on a 3x3 grid."""
from .base import NOOP, TwoPlayerBoardGame

LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columns
    (0, 4, 8), (2, 4, 6),             # diagonals
]


class TicTacToe(TwoPlayerBoardGame):
    code = "ttt"
    name = "Tic-Tac-Toe"
    symbols = ("❌", "⭕")

    @classmethod
    def new_state(cls) -> dict:
        return {"board": [None] * 9, "turn": 0}

    @classmethod
    def apply(cls, state, player, payload):
        if not payload.startswith("m:"):
            return "Tap an empty square."
        idx = int(payload[2:])
        if state["board"][idx] is not None:
            return "That square is taken."
        state["board"][idx] = player
        state["turn"] = 1 - player
        return None

    @classmethod
    def keyboard(cls, state):
        rows = []
        for r in range(3):
            row = []
            for c in range(3):
                i = r * 3 + c
                v = state["board"][i]
                if v is None:
                    row.append(("·", f"m:{i}"))
                else:
                    row.append((cls.symbols[v], NOOP))
            rows.append(row)
        return rows

    @classmethod
    def outcome(cls, state):
        board = state["board"]
        for a, b, c in LINES:
            if board[a] is not None and board[a] == board[b] == board[c]:
                return {"winner": board[a]}
        if all(v is not None for v in board):
            return {"winner": None}
        return None
