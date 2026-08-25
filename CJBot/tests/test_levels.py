"""Relationship XP curve, weighting, and titles."""
from handlers.levels import (
    TITLES, WEIGHTS, level_for_xp, title, xp, xp_for_level,
)
from tests.conftest import FakeUser


def test_curve_strictly_increasing():
    steps = [xp_for_level(n) for n in range(30)]
    assert all(b > a for a, b in zip(steps, steps[1:]))
    assert xp_for_level(0) == 0 and xp_for_level(1) == 150


def test_curve_inverts_cleanly():
    for n in range(1, 26):
        assert level_for_xp(xp_for_level(n)) == n
        assert level_for_xp(xp_for_level(n) - 1) == n - 1
    assert level_for_xp(0) == 0


def test_title_clamps_at_the_end():
    assert title(0) == TITLES[0]
    assert title(len(TITLES) - 1) == TITLES[-1]
    assert title(999) == TITLES[-1]


def test_xp_is_weighted_sum_of_activity(db):
    chat = -1
    db.remember_user(chat, FakeUser(1, "J"))
    db.remember_user(chat, FakeUser(2, "C"))
    # one played-out board game
    gid = db.create_game(chat, "ttt", 1, "J", 2, "C")
    db.update_game(gid, status="finished", state={"board": []})
    # two archived quotes
    db.save_quote(chat, 10, 1, "J", "hello", 2, "C")
    db.save_quote(chat, 11, 2, "C", "goodbye", 1, "J")
    # one finished wordle by a chat member
    db.save_wordle_play(1, "2026-08-20", "J", ["crane"], True, True)
    # one delivered whisper from a member
    wid = db.create_whisper(2, "C", 1, "J", "psst")
    db.mark_whisper_delivered(wid)
    # one cookie ledger entry
    db.add_cookies(chat, 1, 3, "seed")
    assert xp(chat) == (
        WEIGHTS["games"] + 2 * WEIGHTS["quotes"] + WEIGHTS["wordle"]
        + WEIGHTS["whispers"] + WEIGHTS["cookie_moves"]
    )


def test_pending_whisper_and_foreign_activity_excluded(db):
    chat = -1
    db.remember_user(chat, FakeUser(1, "J"))
    db.create_whisper(1, "J", 2, "C", "still sealed")  # never delivered
    db.save_wordle_play(99, "2026-08-20", "Str", ["crane"], True, True)  # not a member
    gid = db.create_game(chat, "ttt", 1, "J", 2, "C")  # pending, no state
    assert xp(chat) == 0
    assert gid  # created but unplayed games earn nothing


def test_announced_level_round_trip(db):
    assert db.get_announced_level(-1) == 0
    db.set_announced_level(-1, 4)
    assert db.get_announced_level(-1) == 4
    db.set_announced_level(-1, 7)
    assert db.get_announced_level(-1) == 7
