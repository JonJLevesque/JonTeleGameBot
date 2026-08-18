"""Chess on the shared board-game framework; rules by python-chess.

Play: tap one of your pieces (it gets [brackets]), then tap a highlighted
square — 🟩 move, 🟥 capture. Castling is the normal two-square king move,
en passant just works, and a pawn reaching the last rank pops up a
promotion picker row. State is a FEN string, so games survive restarts
like every other game. White is the challenger and moves first.
"""
import chess

from .base import NOOP, TwoPlayerBoardGame

# Chess glyphs render in the keyboard's TEXT color, not black/white: on a
# dark theme the "filled" set (♚♛♜…) comes out solid bright — bold and
# white-looking — while the "outline" set (♔♕♖…) stays hollow. So White
# gets the filled set and Black the outline set; that reads correctly (and
# much bolder) on the dark themes this chat uses.
_GLYPHS = {
    "P": "♟", "N": "♞", "B": "♝", "R": "♜", "Q": "♛", "K": "♚",
    "p": "♙", "n": "♘", "b": "♗", "r": "♖", "q": "♕", "k": "♔",
}
_PROMO = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}
_PROMO_ROW = {True: "♛♜♝♞", False: "♕♖♗♘"}  # keyed by chess.WHITE / BLACK


def _sq(r: int, c: int) -> int:
    """Grid position (row 0 = rank 8, White at the bottom) -> chess square."""
    return chess.square(c, 7 - r)


class ChessGame(TwoPlayerBoardGame):
    code = "chess"
    name = "Chess"
    symbols = ("♚", "♔")  # player 0 = White = bold filled glyph (see _GLYPHS)

    @classmethod
    def new_state(cls) -> dict:
        return {"fen": chess.STARTING_FEN, "turn": 0, "sel": None,
                "promo": None, "note": None}

    @classmethod
    def apply(cls, state, player, payload):
        board = chess.Board(state["fen"])

        if state["promo"] is not None:
            if not payload.startswith("p:"):
                return "Pick a promotion piece below (or ↩️ to cancel)."
            choice = payload[2:]
            if choice == "x":
                state["promo"] = None
                return None
            move = chess.Move(
                state["promo"]["f"], state["promo"]["t"], promotion=_PROMO[choice]
            )
            return cls._push(state, board, move)

        if payload.startswith("s:"):
            sq = int(payload[2:])
            piece = board.piece_at(sq)
            if piece is None or piece.color != (player == 0):
                return "That's not your piece."
            if state["sel"] == sq:
                state["sel"] = None  # tap again to deselect
            elif any(m.from_square == sq for m in board.legal_moves):
                state["sel"] = sq
            else:
                return "That piece has no legal moves right now."
            return None

        if payload.startswith("m:"):
            if state["sel"] is None:
                return "Tap one of your pieces first."
            target = int(payload[2:])
            moves = [m for m in board.legal_moves
                     if m.from_square == state["sel"] and m.to_square == target]
            if not moves:
                return "Not a legal move for that piece."
            if moves[0].promotion:
                state["promo"] = {"f": state["sel"], "t": target}
                return None
            return cls._push(state, board, moves[0])

        return "Tap a piece, then a highlighted square."

    @classmethod
    def _push(cls, state, board, move):
        if move not in board.legal_moves:
            return "Not a legal move."
        san = board.san(move)
        board.push(move)
        state["fen"] = board.fen()
        state["turn"] = 0 if board.turn == chess.WHITE else 1
        state["sel"] = None
        state["promo"] = None
        note = f"Last move: {san}"
        if board.is_check() and not board.is_checkmate():
            note += " — check!"
        state["note"] = note
        return None

    @classmethod
    def keyboard(cls, state):
        board = chess.Board(state["fen"])
        sel = state["sel"]
        promo = state["promo"] is not None
        dests = set()
        if sel is not None and not promo:
            dests = {m.to_square for m in board.legal_moves if m.from_square == sel}
        rows = []
        for r in range(8):
            row = []
            for c in range(8):
                sq = _sq(r, c)
                piece = board.piece_at(sq)
                if promo:  # board is frozen while the picker is up
                    row.append((_GLYPHS[piece.symbol()] if piece else "·", NOOP))
                elif sq in dests:
                    row.append(("🟥" if piece else "🟩", f"m:{sq}"))
                elif piece:
                    label = _GLYPHS[piece.symbol()]
                    if sq == sel:
                        label = f"[{label}]"
                    own = piece.color == board.turn
                    row.append((label, f"s:{sq}" if own else NOOP))
                else:
                    row.append(("·", NOOP))
            rows.append(row)
        if promo:
            picker = [(g, f"p:{p}") for g, p in
                      zip(_PROMO_ROW[board.turn], "qrbn")]
            picker.append(("↩️", "p:x"))
            rows.append(picker)
        return rows

    @classmethod
    def outcome(cls, state):
        oc = chess.Board(state["fen"]).outcome()
        if oc is None:
            return None
        if oc.winner is None:
            return {"winner": None}
        return {"winner": 0 if oc.winner == chess.WHITE else 1}

    @classmethod
    def status_line(cls, state, names):
        base = super().status_line(state, names)
        if state["promo"] is not None:
            return f"{base}\n👑 Promotion — pick a piece on the bottom row!"
        if state["sel"] is not None:
            square = chess.square_name(state["sel"])
            return (f"{base}\nSelected {square} — tap 🟩 to move, 🟥 to capture, "
                    f"or the piece again to cancel.")
        return base
