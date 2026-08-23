"""/trivia parsing, shuffling, static picks and payouts."""
import random

import prompts
from handlers.trivia import (
    FIRST_BONUS, REWARD, _recent_static, parse_quiz, payout, pick_static,
    shuffle_quiz,
)

GOOD = "Which planet is hottest?\nMercury\n*Venus\nMars\nJupiter"


def test_parse_quiz_happy_path():
    question, options, correct = parse_quiz(GOOD)
    assert question == "Which planet is hottest?"
    assert options == ["Mercury", "Venus", "Mars", "Jupiter"]
    assert correct == 1


def test_parse_quiz_ignores_blank_lines_and_padding():
    text = "\n Q? \n\n*right \nw1\n w2\nw3\n"
    assert parse_quiz(text) == ("Q?", ["right", "w1", "w2", "w3"], 0)


def test_parse_quiz_rejects_malformed():
    assert parse_quiz(None) is None
    assert parse_quiz("") is None
    assert parse_quiz("Q?\na\nb\nc") is None            # only 3 options
    assert parse_quiz("Q?\na\nb\nc\nd") is None          # no correct marked
    assert parse_quiz("Q?\n*a\n*b\nc\nd") is None        # two marked
    assert parse_quiz("Q?\n*a\nb\nc\nd\ne") is None      # 5 options
    assert parse_quiz("Q?\n*" + "x" * 101 + "\nb\nc\nd") is None
    assert parse_quiz("Q" * 301 + "?\n*a\nb\nc\nd") is None


def test_shuffle_quiz_tracks_correct_answer():
    options = ["a", "b", "c", "d"]
    for seed in range(20):
        shuffled, correct = shuffle_quiz(options, 2, rng=random.Random(seed))
        assert sorted(shuffled) == options
        assert shuffled[correct] == "c"


def test_pick_static_avoids_recent_repeats():
    _recent_static.clear()
    seen = set()
    for _ in range(15):
        question, options, correct = pick_static(-99)
        assert question not in seen
        seen.add(question)
        assert correct == 0 and len(options) == 4


def test_bank_is_well_formed():
    for question, right, wrong in prompts.TRIVIA:
        assert question and len(question) <= 300
        assert right and len(right) <= 100
        assert len(wrong) == 3
        assert all(w and len(w) <= 100 and w != right for w in wrong)


def test_payout_fastest_bonus():
    assert payout(0) == REWARD + FIRST_BONUS
    assert payout(1) == REWARD
    assert payout(5) == REWARD
