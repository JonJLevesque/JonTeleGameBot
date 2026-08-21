"""Shared-pet decay, feeding, cooldowns and the 48h runaway clock."""
from handlers.pet import (
    FEED_HUNGER, PLAY_COOLDOWN, RUNAWAY_AFTER, bar, feed, has_run_away,
    hunger_mood, new_pet, play, play_wait, stage_of, tick,
)

T0 = 1_700_000_000.0
HOUR = 3600.0
DAY = 86400.0


def _pet(**overrides):
    state = new_pet("Waffles", T0, species="🐢")
    state.update(overrides)
    return state


def test_tick_24h_hunger_and_happiness():
    s = _pet(hunger=0.0, happiness=80.0)
    tick(s, T0 + 24 * HOUR)
    assert s["hunger"] == 60.0        # 2.5/h * 24
    assert s["happiness"] == 44.0     # 80 - 1.5/h * 24
    assert s["last_tick"] == T0 + 24 * HOUR


def test_tick_fractional_hours_exact():
    s = _pet(hunger=10.0)
    tick(s, T0 + 90 * 60)             # 1.5h
    assert s["hunger"] == 10.0 + 3.75


def test_tick_clamps_both_ends():
    s = _pet(hunger=95.0, happiness=1.0)
    tick(s, T0 + 100 * HOUR)
    assert s["hunger"] == 100.0
    assert s["happiness"] == 0.0
    # time never runs backwards
    s2 = _pet(hunger=50.0)
    tick(s2, T0 - HOUR)
    assert s2["hunger"] == 50.0


def test_starved_since_backdated_to_crossing():
    # 95 + 2.5/h * 4h = 105 raw: crossed 100 two hours before "now"
    s = _pet(hunger=95.0)
    now = T0 + 4 * HOUR
    tick(s, now)
    assert s["starved_since"] == now - 2 * HOUR


def test_feed_clears_starvation_and_credits_parent():
    s = _pet(hunger=100.0, starved_since=T0)
    assert feed(s, 7, "Cass", T0 + HOUR) == "ok"
    assert s["hunger"] == 100.0 - FEED_HUNGER
    assert s["starved_since"] is None
    assert s["fed_by"]["7"] == {"name": "Cass", "count": 1}


def test_feed_refused_when_stuffed():
    s = _pet(hunger=5.0, happiness=50.0)
    assert feed(s, 7, "Cass", T0) == "refused"
    assert s["hunger"] == 5.0 and s["happiness"] == 50.0 and s["fed_by"] == {}


def test_runaway_only_after_48h_at_100():
    s = _pet(hunger=100.0, starved_since=T0)
    assert not has_run_away(s, T0 + RUNAWAY_AFTER - 1)
    assert has_run_away(s, T0 + RUNAWAY_AFTER)
    assert not has_run_away(_pet(hunger=100.0, starved_since=None), T0 + 10 * DAY)


def test_play_cooldown():
    s = _pet(happiness=50.0, hunger=20.0)
    assert play(s, T0) == "ok"
    assert s["happiness"] == 65.0 and s["hunger"] == 25.0
    assert play(s, T0 + PLAY_COOLDOWN - 1) == "cooldown"
    assert play_wait(s, T0 + PLAY_COOLDOWN - 60) == 60.0
    assert play(s, T0 + PLAY_COOLDOWN) == "ok"


def test_stage_boundaries():
    s = _pet()
    assert stage_of(s, T0 + DAY - 1) == ("egg", "🥚")
    assert stage_of(s, T0 + DAY) == ("baby", "🐢")
    assert stage_of(s, T0 + 7 * DAY) == ("teen", "🐢")
    assert stage_of(s, T0 + 30 * DAY) == ("adult", "🐢")


def test_bar_always_ten_segments():
    for v in (0, 4.9, 5, 50, 99, 100, 120, -3):
        assert len(bar(v)) == 10
    assert bar(0) == "░" * 10
    assert bar(100) == "█" * 10


def test_moods():
    assert hunger_mood(0) == "stuffed"
    assert hunger_mood(50) == "peckish"
    assert hunger_mood(85) == "STARVING"


def test_db_round_trip(db):
    s = _pet(hunger=42.5)
    db.save_pet(-1, s)
    loaded = db.get_pet(-1)
    assert loaded == s
    assert db.all_pets() == [(-1, s)]
    db.clear_pet(-1)
    assert db.get_pet(-1) is None
