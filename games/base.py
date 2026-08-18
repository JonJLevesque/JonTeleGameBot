"""Shared abstraction for turn-based two-player board games.

Game classes are pure logic: state is a JSON-serializable dict, moves come
in as small string payloads (what the Telegram callback data carries after
the routing prefix), and rendering returns a grid of (label, payload)
tuples. Nothing in this package imports telegram — the handler layer owns
the wire format, so adding a game means adding one subclass and one entry
to the registry in games/__init__.py.

Player identity is an index (0 or 1); the handler maps Telegram user ids
to indices. Payload "x" is reserved as a no-op (decorative buttons).
"""
from abc import ABC, abstractmethod

NOOP = "x"

Cell = tuple[str, str]  # (button label, payload)


class TwoPlayerBoardGame(ABC):
    code: str            # short id used in commands, DB and callback data
    name: str            # display name
    symbols: tuple[str, str]  # one emoji per player index

    @classmethod
    @abstractmethod
    def new_state(cls) -> dict:
        """Fresh state; player 0 (the challenger) moves first."""

    @classmethod
    @abstractmethod
    def apply(cls, state: dict, player: int, payload: str) -> str | None:
        """Mutate state with player's move. Return an error string to show
        the player (state unchanged), or None on success. The caller has
        already verified it is `player`'s turn."""

    @classmethod
    @abstractmethod
    def keyboard(cls, state: dict) -> list[list[Cell]]:
        """Board rendered as rows of (label, payload) cells."""

    @classmethod
    @abstractmethod
    def outcome(cls, state: dict) -> dict | None:
        """None while the game is running, otherwise {"winner": 0|1|None}
        where a None winner means a draw."""

    @classmethod
    def status_line(cls, state: dict, names: tuple[str, str]) -> str:
        turn = state["turn"]
        line = f"Turn: {cls.symbols[turn]} {names[turn]}"
        if state.get("note"):
            line = f"{state['note']}\n{line}"
        return line
