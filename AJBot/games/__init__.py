"""Game registry. Add a new game by subclassing TwoPlayerBoardGame and
listing it here — the handler layer picks it up automatically."""
from .base import NOOP, TwoPlayerBoardGame
from .checkers import Checkers
from .chess_game import ChessGame
from .reversi import Reversi
from .tictactoe import TicTacToe

GAME_REGISTRY: dict[str, type[TwoPlayerBoardGame]] = {
    cls.code: cls for cls in (TicTacToe, Reversi, Checkers, ChessGame)
}

__all__ = ["GAME_REGISTRY", "NOOP", "TwoPlayerBoardGame"]
