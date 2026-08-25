"""Checkers (English draughts) on an 8x8 board.

Rules implemented: men move one step diagonally forward, kings one step in
any diagonal direction; captures jump over an adjacent enemy piece and are
mandatory (if any of your pieces can capture, you must capture); multi-jumps
continue with the same piece; reaching the far row promotes to king and ends
the turn. A player with no pieces or no legal moves loses.

Board cells: None, or one of 'a'/'A' (player 0 man/king, starts at the
bottom moving up) and 'b'/'B' (player 1, starts at the top moving down).
Interaction is two-tap: select a piece (payload "s:i"), then a highlighted
destination (payload "m:i").
"""
from .base import NOOP, TwoPlayerBoardGame

MAN, KING = ("a", "b"), ("A", "B")


def _owner(v):
    if v in ("a", "A"):
        return 0
    if v in ("b", "B"):
        return 1
    return None


def _dirs(v):
    if v == "a":
        return [(-1, -1), (-1, 1)]
    if v == "b":
        return [(1, -1), (1, 1)]
    return [(-1, -1), (-1, 1), (1, -1), (1, 1)]  # kings


def _steps(board, i):
    r, c = divmod(i, 8)
    out = []
    for dr, dc in _dirs(board[i]):
        nr, nc = r + dr, c + dc
        if 0 <= nr < 8 and 0 <= nc < 8 and board[nr * 8 + nc] is None:
            out.append(nr * 8 + nc)
    return out


def _captures(board, i):
    """[(landing, captured), ...] jumps available to the piece at i."""
    r, c = divmod(i, 8)
    v = board[i]
    out = []
    for dr, dc in _dirs(v):
        lr, lc = r + 2 * dr, c + 2 * dc
        if not (0 <= lr < 8 and 0 <= lc < 8):
            continue
        mid = (r + dr) * 8 + (c + dc)
        land = lr * 8 + lc
        if board[land] is None and _owner(board[mid]) == 1 - _owner(v):
            out.append((land, mid))
    return out


def _pieces(board, player):
    return [i for i in range(64) if _owner(board[i]) == player]


def _must_capture(board, player):
    return any(_captures(board, i) for i in _pieces(board, player))


def _has_move(board, player):
    return any(_captures(board, i) or _steps(board, i) for i in _pieces(board, player))


class Checkers(TwoPlayerBoardGame):
    code = "checkers"
    name = "Checkers"
    symbols = ("🔴", "⚪")
    king_symbols = ("🟥", "⬜")

    @classmethod
    def new_state(cls) -> dict:
        board = [None] * 64
        for i in range(64):
            r, c = divmod(i, 8)
            if (r + c) % 2 == 1:
                if r < 3:
                    board[i] = "b"
                elif r > 4:
                    board[i] = "a"
        return {"board": board, "turn": 0, "sel": None, "chain": None, "note": None}

    @classmethod
    def apply(cls, state, player, payload):
        board = state["board"]
        kind, _, arg = payload.partition(":")
        if kind not in ("s", "m") or not arg.isdigit():
            return "Tap one of your pieces."
        idx = int(arg)

        if kind == "s":
            if state["chain"] is not None:
                return "You must continue jumping with the same piece."
            if _owner(board[idx]) != player:
                return "That's not your piece."
            if idx == state["sel"]:
                state["sel"] = None  # tap again to deselect
                return None
            if _must_capture(board, player) and not _captures(board, idx):
                return "A capture is available — you must play a capturing piece."
            if not _captures(board, idx) and not _steps(board, idx):
                return "That piece has no moves."
            state["sel"] = idx
            return None

        # kind == "m": move the selected piece
        sel = state["sel"]
        if sel is None:
            return "Select one of your pieces first."
        caps = _captures(board, sel)
        captured = None
        if caps:
            match = [mid for land, mid in caps if land == idx]
            if not match:
                return "You must take the capture (🟢 squares)."
            captured = match[0]
        elif idx not in _steps(board, sel):
            return "Not a legal move — pick a 🟢 square."

        piece = board[sel]
        board[sel] = None
        if captured is not None:
            board[captured] = None
        promoted = False
        if piece == "a" and idx // 8 == 0:
            piece, promoted = "A", True
        elif piece == "b" and idx // 8 == 7:
            piece, promoted = "B", True
        board[idx] = piece

        state["note"] = None
        if captured is not None and not promoted and _captures(board, idx):
            # multi-jump: same player continues with this piece
            state["sel"] = idx
            state["chain"] = idx
            state["note"] = f"{cls.symbols[player]} continues the jump!"
        else:
            state["sel"] = None
            state["chain"] = None
            state["turn"] = 1 - player
        return None

    @classmethod
    def keyboard(cls, state):
        board, sel = state["board"], state["sel"]
        dests = {}
        if sel is not None:
            caps = _captures(board, sel)
            dests = {land for land, _ in caps} if caps else set(_steps(board, sel))
        rows = []
        for r in range(8):
            row = []
            for c in range(8):
                i = r * 8 + c
                v = board[i]
                if (r + c) % 2 == 0:
                    row.append(("　", NOOP))  # light squares are never playable
                elif v is not None:
                    p = _owner(v)
                    label = cls.king_symbols[p] if v.isupper() else cls.symbols[p]
                    if i == sel:
                        label = f"({label})"
                    row.append((label, f"s:{i}"))
                elif i in dests:
                    row.append(("🟢", f"m:{i}"))
                else:
                    row.append(("·", NOOP))
            rows.append(row)
        return rows

    @classmethod
    def outcome(cls, state):
        player = state["turn"]
        board = state["board"]
        if not _pieces(board, player) or not _has_move(board, player):
            return {"winner": 1 - player}
        return None

    @classmethod
    def status_line(cls, state, names):
        base = super().status_line(state, names)
        return f"{base}\nKings: {cls.king_symbols[0]}/{cls.king_symbols[1]} · tap a piece, then a 🟢 square"
