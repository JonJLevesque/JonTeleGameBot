"""Truth-or-dare bag randomness: fair every four draws, never streaky."""
from handlers.party import TOD_BAG, _bag_draw


def _draw_n(n, bag=None):
    bag = list(bag or [])
    out = []
    for _ in range(n):
        choice, bag = _bag_draw(bag)
        out.append(choice)
    return out, bag


def test_full_bag_is_exactly_two_of_each():
    draws, bag = _draw_n(4)
    assert sorted(draws) == ["dare", "dare", "truth", "truth"]
    assert bag == []


def test_every_bag_cycle_stays_balanced():
    draws, _ = _draw_n(40)
    for i in range(0, 40, 4):
        assert sorted(draws[i:i + 4]) == ["dare", "dare", "truth", "truth"]


def test_streaks_within_a_bag_cap_at_two():
    draws, _ = _draw_n(400)
    for i in range(0, 400, 4):
        window = draws[i:i + 4]
        assert window != ["truth", "truth", "truth", "truth"]
        assert window[:3] != ["truth"] * 3 and window[1:] != ["truth"] * 3
        assert window[:3] != ["dare"] * 3 and window[1:] != ["dare"] * 3


def test_partial_bag_is_consumed_before_refill():
    draws, bag = _draw_n(1, ["dare"])
    assert draws == ["dare"] and bag == []


def test_bag_db_round_trip(db):
    assert db.get_tod_bag(-1, 1) == []
    db.set_tod_bag(-1, 1, ["truth", "dare"])
    assert db.get_tod_bag(-1, 1) == ["truth", "dare"]
    db.set_tod_bag(-1, 1, [])
    assert db.get_tod_bag(-1, 1) == []


def test_bag_template_unchanged_by_draws():
    _draw_n(20)
    assert TOD_BAG == ["truth", "truth", "dare", "dare"]
