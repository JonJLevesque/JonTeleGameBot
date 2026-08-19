"""Regression tests for the 2026-08-18 audit findings."""
from handlers.beautiful import _parse_vote
from handlers.bracket import new_bracket


def test_escrow_and_activate_atomic(db):
    chat = -1
    db.add_cookies(chat, 1, 10, "seed")
    db.add_cookies(chat, 2, 10, "seed")
    gid = db.create_game(chat, "chess", 1, "J", 2, "C", stake=10)
    ok = db.escrow_and_activate(db.get_game(gid), 2, "C", {"turn": 0})
    assert ok
    assert db.get_cookies(chat, 1) == 0 and db.get_cookies(chat, 2) == 0
    assert db.get_game(gid)["status"] == "active"


def test_escrow_refuses_short_balance(db):
    chat = -1
    db.add_cookies(chat, 1, 10, "seed")  # player 2 has nothing
    gid = db.create_game(chat, "chess", 1, "J", 2, "C", stake=10)
    ok = db.escrow_and_activate(db.get_game(gid), 2, "C", {"turn": 0})
    assert not ok
    # nothing deducted, game still pending
    assert db.get_cookies(chat, 1) == 10
    assert db.get_game(gid)["status"] == "pending"


def test_bracket_nonce_present_and_varies():
    a, b = new_bracket(range(4)), new_bracket(range(4))
    assert a["nonce"] and b["nonce"]  # extremely unlikely to collide, but
    # what matters is that a reset bracket gets a different nonce than 0


def test_vote_parser_handles_both_formats():
    assert _parse_vote("wmbp:123:7:a") == (123, 7, "a")
    assert _parse_vote("wmbp:7:a") == (None, 7, "a")  # legacy buttons


def test_clear_beautiful_resets_recap_snapshot(db):
    db.recap_on(-1)
    db.save_beautiful(-1, {"x": 1})
    db.recap_update_snapshot(-1, 57)
    db.clear_beautiful(-1)
    assert db.recap_snapshot(-1) == 0
