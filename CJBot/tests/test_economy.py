from handlers.boardgames import _payout
from handlers.tournament import _parse


def test_escrow_winner_takes_pot(db):
    chat = -1
    db.add_cookies(chat, 1, 30, "seed")
    db.add_cookies(chat, 2, 30, "seed")
    gid = db.create_game(chat, "chess", 1, "J", 2, "C", stake=10)
    db.add_cookies(chat, 1, -10, "escrow")
    db.add_cookies(chat, 2, -10, "escrow")
    _payout(db.get_game(gid), winner=0)
    assert db.get_cookies(chat, 1) == 40
    assert db.get_cookies(chat, 2) == 20


def test_escrow_draw_refunds(db):
    chat = -1
    db.add_cookies(chat, 1, 10, "seed")
    db.add_cookies(chat, 2, 10, "seed")
    gid = db.create_game(chat, "ttt", 1, "J", 2, "C", stake=5)
    db.add_cookies(chat, 1, -5, "escrow")
    db.add_cookies(chat, 2, -5, "escrow")
    _payout(db.get_game(gid), winner=None)
    assert db.get_cookies(chat, 1) == 10
    assert db.get_cookies(chat, 2) == 10


def test_no_stake_no_payout(db):
    gid = db.create_game(-1, "ttt", 1, "J", 2, "C")
    assert _payout(db.get_game(gid), 0) == ""


def test_shop_lifecycle(db):
    i = db.shop_add(-1, 25, "loser cooks dinner")
    assert db.shop_get(-1, i)["price"] == 25
    assert db.shop_get(-2, i) is None  # other chats can't see it
    assert db.shop_remove(-1, i)
    assert not db.shop_list(-1)


def test_cookie_log_deltas(db):
    db.add_cookies(-1, 1, 12, "win")
    db.add_cookies(-1, 1, -3, "redeem")
    db.add_cookies(-1, 2, 4, "win")
    assert dict(db.cookie_deltas_since(-1, "2000-01-01")) == {1: 9, 2: 4}


def test_tournament_parse():
    t, items = _parse("Movie Night: Dune, Inception,  Parasite , dune")
    assert t == "Movie Night" and items == ["Dune", "Inception", "Parasite"]
    t, items = _parse("Trips:\nParis, France\nTokyo")
    assert items == ["Paris, France", "Tokyo"]
