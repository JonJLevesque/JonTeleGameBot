"""Casino pure logic: slots payout table EV and blackjack rules."""
from handlers.casino import (
    dealer_play, fresh_deck, hand_value, is_blackjack, reels, settle,
    slots_payout,
)

# card helper: rank 0..12 (A..K), suit 0..3
def c(rank, suit=0):
    return suit * 13 + rank

A, TEN, J, Q, K = 0, 9, 10, 11, 12


# --------------------------------------------------------------------- slots

def test_slots_expected_value_in_house_range():
    stake = 10
    ev = sum(int(stake * slots_payout(v, stake)[0]) for v in range(1, 65))
    ev /= 64 * stake
    assert 0.85 <= ev <= 0.95, ev


def test_slots_payout_table():
    assert slots_payout(64, 10)[0] == 10          # 777 jackpot
    for v in (1, 22, 43):                          # other triples
        assert slots_payout(v, 10)[0] == 5
    # value 2 -> digits (1,0,0): no first-two match, last two match
    assert slots_payout(2, 10)[0] == 1
    # value 5 -> digits (0,1,0): nothing matches in order (d0!=d1, d1!=d2)
    assert slots_payout(5, 10)[0] == 0
    # value 4 -> digits (3,0,0): last two match
    assert slots_payout(4, 10)[0] == 1
    # first-two match, non-triple: digits (1,1,0) -> v-1 = 1+4 = 5 -> v=6
    assert slots_payout(6, 10)[0] == 1.5


def test_reels_roundtrip():
    assert reels(1) == (0, 0, 0)
    assert reels(64) == (3, 3, 3)
    assert reels(22) == (1, 1, 1)
    assert reels(43) == (2, 2, 2)


# ----------------------------------------------------------------- blackjack

def test_deck_integrity():
    d = fresh_deck()
    assert len(d) == 52 and len(set(d)) == 52
    assert min(d) == 0 and max(d) == 51


def test_hand_values_with_aces():
    assert hand_value([c(A), c(K)]) == 21
    assert is_blackjack([c(A), c(K)])
    assert hand_value([c(A), c(A, 1), c(TEN - 1)]) == 21   # A+A+9
    assert hand_value([c(A), c(A, 1), c(A, 2), c(7)]) == 21  # A+A+A+8
    assert hand_value([c(A), c(5)]) == 17                  # A + 6: soft 17
    assert hand_value([c(K), c(Q), c(1)]) == 22            # bust stays bust
    assert not is_blackjack([c(7), c(6), c(7)])            # 21 in 3 isn't BJ


def test_dealer_stands_17_hits_16():
    deck = [c(1)]
    dealer = [c(6), c(TEN)]  # 7 + 10: hard 17
    dealer_play(deck, dealer)
    assert len(dealer) == 2 and deck  # stood, no card drawn
    dealer = [c(A), c(5)]  # A + 6: soft 17, stands on ALL 17s
    dealer_play(deck, dealer)
    assert len(dealer) == 2
    deck = [c(K)]
    dealer = [c(5), c(TEN)]  # 6 + 10 = 16 must hit
    dealer_play(deck, dealer)
    assert len(dealer) == 3 and hand_value(dealer) == 26


def test_settle_matrix():
    bj = [c(A), c(K)]
    twenty = [c(TEN), c(Q)]
    nineteen = [c(TEN - 1), c(K)]  # 9 + 10
    bust = [c(K), c(Q), c(2)]
    # blackjack vs blackjack pushes the stake back
    assert settle(bj, [c(A, 1), c(K, 1)], 10, False, True)[0] == 10
    # blackjack pays 3:2
    assert settle(bj, nineteen, 10, False, True)[0] == 25
    # bust loses everything, even against a dealer bust
    assert settle(bust, bust, 10, False, False)[0] == 0
    # dealer bust pays even money
    assert settle(twenty, bust, 10, False, False)[0] == 20
    # higher total wins, lower loses, equal pushes
    assert settle(twenty, nineteen, 10, False, False)[0] == 20
    assert settle(nineteen, twenty, 10, False, False)[0] == 0
    assert settle(twenty, twenty, 10, False, False)[0] == 10
    # dealer blackjack beats a plain 21... and any 20
    assert settle(twenty, bj, 10, False, False)[0] == 0


def test_settle_doubling_doubles_everything():
    twenty = [c(TEN), c(Q), c(0, 3)]  # doubled hands have 3 cards
    nineteen = [c(TEN - 1), c(K)]
    assert hand_value(twenty) == 21  # 10+10+A
    win = settle(twenty, nineteen, 10, True, False)
    assert win[0] == 40  # doubled pot of 20, paid even money
    push = settle(nineteen + [c(0, 2)], [c(K, 2), c(K, 3)], 10, True, False)
    assert hand_value(nineteen + [c(0, 2)]) == 20
    assert push[0] == 20  # doubled stake returned on push


def test_casino_hand_persistence(db):
    hid = db.create_casino_hand(-1, 7, 10, {"player": [1, 2]})
    hand = db.get_casino_hand(hid)
    assert hand["stake"] == 10 and hand["status"] == "active"
    assert db.active_casino_hand(-1, 7)["id"] == hid
    db.update_casino_hand(hid, status="finished")
    assert db.active_casino_hand(-1, 7) is None
