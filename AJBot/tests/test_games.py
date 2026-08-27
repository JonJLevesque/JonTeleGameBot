import chess as chesslib

from games import GAME_REGISTRY
from handlers.taboo import _forbidden
from handlers.wordle import score_guess


# ------------------------------------------------------------------- wordle

def test_wordle_scoring_duplicates():
    assert score_guess("tribe", "tribe") == ["g"] * 5
    assert score_guess("eerie", "tribe") == ["b", "b", "y", "y", "g"]
    assert score_guess("allee", "eagle") == ["y", "y", "b", "y", "g"]
    assert score_guess("speed", "abide") == ["b", "b", "y", "b", "y"]


# -------------------------------------------------------------------- taboo

def test_taboo_stopwords_are_free():
    assert _forbidden("seen but no reply") == {"seen", "reply"}
    assert _forbidden("I love you") == {"love"}


def test_taboo_never_empty():
    import prompts
    for p in prompts.TABOO_PHRASES + prompts.TABOO_PHRASES_SPICY:
        assert _forbidden(p)


# -------------------------------------------------------------------- chess

def _move(G, state, uci):
    m = chesslib.Move.from_uci(uci)
    assert G.apply(state, state["turn"], f"s:{m.from_square}") is None
    assert G.apply(state, state["turn"], f"m:{m.to_square}") is None


def test_chess_fools_mate():
    G = GAME_REGISTRY["chess"]
    s = G.new_state()
    for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):
        _move(G, s, uci)
    assert G.outcome(s) == {"winner": 1}


def test_chess_promotion_picker():
    G = GAME_REGISTRY["chess"]
    s = G.new_state()
    s["fen"] = "8/P6k/8/8/8/8/7K/8 w - - 0 1"
    assert G.apply(s, 0, f"s:{chesslib.A7}") is None
    assert G.apply(s, 0, f"m:{chesslib.A8}") is None
    assert s["promo"] is not None
    assert G.apply(s, 0, "p:q") is None
    assert "a8=Q" in s["note"]


def test_chess_guards():
    G = GAME_REGISTRY["chess"]
    s = G.new_state()
    assert G.apply(s, 0, f"s:{chesslib.E7}") == "That's not your piece."
