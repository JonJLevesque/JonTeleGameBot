"""Shared-pet decay, feeding, cooldowns and the 48h runaway clock."""
import handlers.pet as pet
from handlers.pet import (
    FEED_HUNGER, PLAY_COOLDOWN, RUNAWAY_AFTER, TALK_BOOST_COOLDOWN,
    TALK_HAPPY, bar, feed, has_run_away, hunger_mood, new_pet, play,
    play_wait, stage_of, talk_boost, tick,
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


def test_talk_boost_bump_and_cooldown():
    s = _pet(happiness=50.0)
    assert talk_boost(s, T0)
    assert s["happiness"] == 50.0 + TALK_HAPPY
    # chatting again inside the window: no extra happiness
    assert not talk_boost(s, T0 + TALK_BOOST_COOLDOWN - 1)
    assert s["happiness"] == 50.0 + TALK_HAPPY
    assert talk_boost(s, T0 + TALK_BOOST_COOLDOWN)
    assert s["happiness"] == 50.0 + 2 * TALK_HAPPY


def test_talk_boost_caps_at_100():
    s = _pet(happiness=99.5)
    assert talk_boost(s, T0)
    assert s["happiness"] == 100.0


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


# ------------------------------------------------------------ new actions

class _Rng:
    def __init__(self, v): self.v = v
    def random(self): return self.v
    def choice(self, seq): return seq[0]


def test_adore_bumps_and_per_person_cooldown():
    p = _pet(happiness=50.0)
    assert pet.adore(p, 1, "A", 0) == "ok"
    assert p["happiness"] == 58.0
    assert pet.adore(p, 1, "A", 60) == "cooldown"
    assert pet.adore(p, 2, "B", 60) == "ok"            # different person
    assert pet.adore(p, 1, "A", pet.ADORE_COOLDOWN + 1) == "ok"
    assert p["adored_by"]["1"]["count"] == 2


def test_train_gates_and_outcomes():
    p = _pet(happiness=30.0)
    assert pet.train(p, "sit", 0, rng=_Rng(0.0)) == "mopey"
    p["happiness"] = 100.0
    assert pet.train(p, "sit", 0, rng=_Rng(0.0)) == "learned"
    assert pet.train(p, "SIT", 0, rng=_Rng(0.0)) == "known"
    assert pet.train(p, "roll", 0, rng=_Rng(0.99)) == "failed"
    assert p["tricks"] == ["sit"]
    p["tricks"] = [f"t{i}" for i in range(pet.TRAIN_MAX_TRICKS)]
    assert pet.train(p, "new", 0, rng=_Rng(0.0)) == "full"


def test_train_chance_scales_with_happiness():
    assert pet.train_chance(pet.TRAIN_MIN_HAPPY) == 0.4
    assert pet.train_chance(100) == 0.9
    assert pet.train_chance(0) == 0.4


def test_trick_cooldown():
    p = _pet(tricks=["sit"], happiness=50.0)
    assert pet.perform_trick(p, 0, rng=_Rng(0)) == "sit"
    assert pet.perform_trick(p, 10, rng=_Rng(0)) is None
    assert pet.perform_trick(p, pet.TRICK_COOLDOWN + 1, rng=_Rng(0)) == "sit"
    assert pet.perform_trick(_pet(), 0) is None


def test_treat_once_per_day():
    p = _pet(happiness=50.0, hunger=50.0)
    assert pet.treat(p, "2026-08-25") == "ok"
    assert (p["happiness"], p["hunger"]) == (75.0, 40.0)
    assert pet.treat(p, "2026-08-25") == "had_one"
    assert pet.treat(p, "2026-08-26") == "ok"


def test_walk_cooldown_and_appetite():
    p = _pet(happiness=50.0, hunger=10.0)
    assert pet.walk(p, 0) == "ok"
    assert (p["happiness"], p["hunger"]) == (60.0, 18.0)
    assert pet.walk(p, 60) == "cooldown"
    assert pet.walk(p, pet.WALK_COOLDOWN) == "ok"


def test_sleep_halves_hunger_and_pauses_moping():
    p = _pet(hunger=0.0, happiness=50.0, last_tick=0.0)
    assert pet.put_to_sleep(p, 0) == "ok"
    assert pet.put_to_sleep(p, 1) == "asleep"
    pet.tick(p, 4 * 3600)                       # 4h asleep
    assert p["hunger"] == 4 * pet.HUNGER_PER_HOUR * pet.SLEEP_HUNGER_FACTOR
    assert p["happiness"] == 50.0
    pet.tick(p, 12 * 3600)                      # 4h more asleep, then 4h awake
    assert p["hunger"] == 8 * pet.HUNGER_PER_HOUR * 0.5 + 4 * pet.HUNGER_PER_HOUR
    assert p["happiness"] == 50.0 - 4 * pet.HAPPY_PER_HOUR
    assert pet.is_asleep(p, 12 * 3600) is False
    assert pet.maybe_wake(p, 12 * 3600) is True     # announced once…
    assert pet.maybe_wake(p, 13 * 3600) is False    # …and only once
    assert p["happiness"] == 50.0 - 4 * pet.HAPPY_PER_HOUR + pet.WAKE_HAPPY


def test_parents_board_merges_feeders_and_fans():
    p = _pet()
    p["fed_by"] = {"1": {"name": "A", "count": 3}, "2": {"name": "B", "count": 1}}
    p["adored_by"] = {"2": {"name": "Bee", "count": 5, "last": 0}, "3": {"name": "C", "count": 2, "last": 0}}
    assert pet.parents_board(p) == [("A", 3, 0), ("Bee", 1, 5), ("C", 0, 2)]
