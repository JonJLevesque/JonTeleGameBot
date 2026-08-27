"""Reversi/Othello on an 8x8 board.

Standard rules: a move must flip at least one opposing disc; a player with
no legal move passes automatically; the game ends when neither side can
move (or the board is full) and the higher disc count wins.
"""
from .base import NOOP, TwoPlayerBoardGame

DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _flips(board, idx, player):
    """All opposing disc indices flipped by playing `idx`, [] if illegal."""
    if board[idx] is not None:
        return []
    r0, c0 = divmod(idx, 8)
    flipped = []
    for dr, dc in DIRS:
        line = []
        r, c = r0 + dr, c0 + dc
        while 0 <= r < 8 and 0 <= c < 8:
            v = board[r * 8 + c]
            if v is None:
                break
            if v == player:
                flipped.extend(line)
                break
            line.append(r * 8 + c)
            r, c = r + dr, c + dc
    return flipped


def _legal_moves(board, player):
    return [i for i in range(64) if board[i] is None and _flips(board, i, player)]


class Reversi(TwoPlayerBoardGame):
    code = "reversi"
    name = "Reversi"
    symbols = ("⚫", "⚪")

    @classmethod
    def new_state(cls) -> dict:
        board = [None] * 64
        board[27], board[36] = 1, 1
        board[28], board[35] = 0, 0
        return {"board": board, "turn": 0, "note": None}

    @classmethod
    def apply(cls, state, player, payload):
        if not payload.startswith("m:"):
            return "Tap one of the highlighted squares."
        idx = int(payload[2:])
        board = state["board"]
        flipped = _flips(board, idx, player)
        if not flipped:
            return "Not a legal move — pick a 🟩 square."
        board[idx] = player
        for i in flipped:
            board[i] = player
        state["note"] = None
        opponent = 1 - player
        if _legal_moves(board, opponent):
            state["turn"] = opponent
        elif _legal_moves(board, player):
            state["turn"] = player
            state["note"] = f"{cls.symbols[opponent]} has no legal moves — turn passes."
        # otherwise nobody can move; outcome() will end the game
        return None

    @classmethod
    def keyboard(cls, state):
        board, turn = state["board"], state["turn"]
        legal = set(_legal_moves(board, turn))
        rows = []
        for r in range(8):
            row = []
            for c in range(8):
                i = r * 8 + c
                if board[i] is not None:
                    row.append((cls.symbols[board[i]], NOOP))
                elif i in legal:
                    row.append(("🟩", f"m:{i}"))
                else:
                    row.append(("·", NOOP))
            rows.append(row)
        return rows

    @classmethod
    def outcome(cls, state):
        board = state["board"]
        if _legal_moves(board, 0) or _legal_moves(board, 1):
            return None
        black = sum(1 for v in board if v == 0)
        white = sum(1 for v in board if v == 1)
        if black == white:
            return {"winner": None, "score": (black, white)}
        return {"winner": 0 if black > white else 1, "score": (black, white)}

    @classmethod
    def status_line(cls, state, names):
        board = state["board"]
        black = sum(1 for v in board if v == 0)
        white = sum(1 for v in board if v == 1)
        base = super().status_line(state, names)
        return f"{cls.symbols[0]} {black} — {white} {cls.symbols[1]}\n{base}"
