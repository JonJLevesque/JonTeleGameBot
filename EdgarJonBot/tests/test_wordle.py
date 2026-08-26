import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
from datetime import date  # noqa: E402
import db  # noqa: E402
from handlers import wordle  # noqa: E402


def test_score_guess_duplicates():
    assert wordle.score_guess("crane", "crane") == ["g"] * 5
    assert wordle.score_guess("allee", "eagle") == ["y", "y", "b", "y", "g"]
    assert wordle.score_guess("speed", "abide") == ["b", "b", "y", "b", "y"]


def test_streak_and_duel():
    db.init(":memory:")
    today = date(2026, 8, 26)
    for d, won, g in [("2026-08-26", True, 3), ("2026-08-25", True, 4), ("2026-08-23", True, 2)]:
        db.save_wordle_play(1, d, "Jon", ["x"] * g, True, won)
    assert wordle.streak(1, today) == 2
    db.save_wordle_play(2, "2026-08-26", "Edgar", ["x"] * 5, True, True)
    db.save_wordle_play(3, "2026-08-26", "Loser", ["x"] * 6, True, False)
    a, b, c = db.wordle_play(1, "2026-08-26"), db.wordle_play(2, "2026-08-26"), db.wordle_play(3, "2026-08-26")
    w, ca, cb = wordle.duel_result(a, b)
    assert (w["user_id"], ca, cb) == (1, 3, 5)
    assert wordle.duel_result(b, c)[0]["user_id"] == 2 and wordle.cost(c) == 7
    assert wordle.duel_result(a, a)[0] is None
    db.save_wordle_duel(9, "2026-08-26", 1)
    assert db.wordle_duel_wins(9, 1) == 1 and db.wordle_duel_wins(9, 1, "2026-08-27") == 0


def test_word_lists_present():
    answers, allowed = wordle._load_words()
    assert len(answers) > 2000 and "crane" in allowed
