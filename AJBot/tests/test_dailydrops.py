"""Daily-claim streaks and supply-drop pacing."""
import random
from datetime import date

from handlers.dailydrops import (
    DropState, daily_reward, roll_drop, trap_loss,
)


def test_daily_reward_curve():
    assert daily_reward(1) == 2
    assert daily_reward(2) == 3
    assert daily_reward(5) == 6
    assert daily_reward(6) == 7
    assert daily_reward(100) == 7  # capped


def test_daily_claim_first_and_same_day(db):
    assert db.daily_claim(-1, 1, "2026-08-20", "2026-08-19") == (True, 1)
    assert db.daily_claim(-1, 1, "2026-08-20", "2026-08-19") == (False, 1)


def test_daily_claim_streak_grows_and_resets(db):
    db.daily_claim(-1, 1, "2026-08-20", "2026-08-19")
    assert db.daily_claim(-1, 1, "2026-08-21", "2026-08-20") == (True, 2)
    assert db.daily_claim(-1, 1, "2026-08-22", "2026-08-21") == (True, 3)
    # a gap day starts over
    assert db.daily_claim(-1, 1, "2026-08-25", "2026-08-24") == (True, 1)


def test_daily_claim_is_per_user_and_chat(db):
    db.daily_claim(-1, 1, "2026-08-20", "2026-08-19")
    assert db.daily_claim(-1, 2, "2026-08-20", "2026-08-19") == (True, 1)
    assert db.daily_claim(-2, 1, "2026-08-20", "2026-08-19") == (True, 1)


def test_drop_fires_exactly_at_threshold():
    st = DropState(random.Random(0))
    d = date(2026, 8, 20)
    for _ in range(st.threshold - 1):
        assert not st.register_message(d)
    assert st.register_message(d)
    assert st.count == 0  # counter reset for the next cycle


def test_threshold_redrawn_in_range():
    # Distinct dates so the daily cap never blocks the cycle under test.
    st = DropState(random.Random(1))
    lo, hi = DropState.THRESHOLD_RANGE
    for day in range(1, 6):
        d = date(2026, 8, day)
        threshold = st.threshold
        for _ in range(threshold - st.count - 1):
            assert not st.register_message(d)
        assert st.register_message(d)
        assert lo <= st.threshold <= hi


def test_daily_cap_enforced_and_resets():
    st = DropState(random.Random(2))
    drops = sum(st.register_message(date(2026, 8, 20)) for _ in range(10_000))
    assert drops == DropState.DAILY_CAP
    drops = sum(st.register_message(date(2026, 8, 21)) for _ in range(10_000))
    assert drops == DropState.DAILY_CAP


def test_claim_drop_first_tap_wins(db):
    did = db.create_drop(-1, "crate", 5)
    row = db.claim_drop(did, 1)
    assert row["kind"] == "crate" and row["amount"] == 5
    assert db.claim_drop(did, 2) is None
    assert db.claim_drop(999, 1) is None  # unknown drop


def test_roll_drop_bounds_and_mix():
    rng = random.Random(3)
    rolls = [roll_drop(rng) for _ in range(1000)]
    kinds = {k for k, _ in rolls}
    assert kinds == {"crate", "trap"}
    assert all(3 <= a <= 8 for _, a in rolls)
    trap_rate = sum(1 for k, _ in rolls if k == "trap") / len(rolls)
    assert 0.1 < trap_rate < 0.3


def test_trap_loss_clamps_to_balance():
    assert trap_loss(5, 10) == 5
    assert trap_loss(5, 3) == 3
    assert trap_loss(5, 0) == 0
    assert trap_loss(5, -2) == 0  # defensive: never amplify a negative
