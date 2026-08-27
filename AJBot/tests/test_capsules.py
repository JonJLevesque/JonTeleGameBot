"""Scheduled whispers and time capsules: parsing + due/sealed db behavior."""
from datetime import datetime, timedelta, timezone

from handlers.common import LOCAL_TZ
from handlers.pigeon import parse_capsule_duration, parse_schedule

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=LOCAL_TZ)  # a Thursday, noon local


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------ parse_schedule

def test_relative_hours():
    at, rest = parse_schedule(["in", "2h", "hello", "there"], now=NOW)
    assert at == _utc(NOW + timedelta(hours=2))
    assert rest == ["hello", "there"]


def test_relative_minutes_and_days():
    assert parse_schedule(["in", "30m", "x"], now=NOW)[0] == _utc(
        NOW + timedelta(minutes=30))
    assert parse_schedule(["in", "3d", "x"], now=NOW)[0] == _utc(
        NOW + timedelta(days=3))


def test_in_without_duration_is_message():
    at, rest = parse_schedule(["in", "a", "way", "you", "were", "right"], now=NOW)
    assert at is None
    assert rest == ["in", "a", "way", "you", "were", "right"]


def test_at_future_time_today():
    at, rest = parse_schedule(["at", "21:30", "goodnight"], now=NOW)
    assert at == _utc(NOW.replace(hour=21, minute=30))
    assert rest == ["goodnight"]


def test_at_past_time_rolls_to_tomorrow():
    at, _ = parse_schedule(["at", "9am", "morning!"], now=NOW)
    assert at == _utc(NOW.replace(hour=9, minute=0) + timedelta(days=1))


def test_at_ampm_conversion():
    at, _ = parse_schedule(["at", "9:30pm", "x"], now=NOW)
    assert at == _utc(NOW.replace(hour=21, minute=30))
    at, _ = parse_schedule(["at", "12am", "x"], now=NOW)  # midnight -> tomorrow
    assert at == _utc(NOW.replace(hour=0, minute=0) + timedelta(days=1))


def test_at_invalid_times_are_message():
    for spec in ("25:00", "13pm", "9:99", "first"):
        at, rest = parse_schedule(["at", spec, "x"], now=NOW)
        assert at is None
        assert rest == ["at", spec, "x"]


def test_tomorrow_default_9am():
    at, rest = parse_schedule(["tomorrow", "good", "luck"], now=NOW)
    assert at == _utc(NOW.replace(hour=9, minute=0) + timedelta(days=1))
    assert rest == ["good", "luck"]


def test_tomorrow_with_time():
    at, rest = parse_schedule(["tomorrow", "8am", "good", "luck"], now=NOW)
    assert at == _utc(NOW.replace(hour=8, minute=0) + timedelta(days=1))
    assert rest == ["good", "luck"]


def test_plain_message_untouched():
    at, rest = parse_schedule(["you", "were", "right"], now=NOW)
    assert at is None
    assert rest == ["you", "were", "right"]


# ---------------------------------------------------- parse_capsule_duration

def test_capsule_durations():
    assert parse_capsule_duration("2w") == timedelta(days=14)
    assert parse_capsule_duration("6mo") == timedelta(days=180)
    assert parse_capsule_duration("1y") == timedelta(days=365)


def test_capsule_duration_rejects_junk():
    for tok in ("2h", "mo", "6months", "soon", "6m"):
        assert parse_capsule_duration(tok) is None


# --------------------------------------------------------------- db sealing

def _ts(delta):
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%d %H:%M:%S")


def test_future_whisper_stays_sealed(db):
    db.create_whisper(2, "Cass", 1, "Jon", "sealed",
                      deliver_at=_ts(timedelta(hours=1)))
    assert db.pending_whispers(1) == []
    assert db.due_whispers() == []


def test_due_whisper_appears_everywhere(db):
    wid = db.create_whisper(2, "Cass", 1, "Jon", "due",
                            deliver_at=_ts(timedelta(minutes=-1)))
    assert [w["id"] for w in db.pending_whispers(1)] == [wid]
    assert [w["id"] for w in db.due_whispers()] == [wid]


def test_immediate_whisper_never_in_due(db):
    db.create_whisper(2, "Cass", 1, "Jon", "now")
    assert len(db.pending_whispers(1)) == 1
    assert db.due_whispers() == []


def test_capsule_kind_round_trips(db):
    db.create_whisper(2, "Cass", 1, "Jon", "old times",
                      deliver_at=_ts(timedelta(minutes=-1)), kind="capsule")
    assert db.pending_whispers(1)[0]["kind"] == "capsule"


def test_teased_flag(db):
    wid = db.create_whisper(2, "Cass", 1, "Jon", "hi",
                            deliver_at=_ts(timedelta(minutes=-1)))
    assert not db.due_whispers()[0]["teased"]
    db.mark_whisper_teased(wid)
    assert db.due_whispers()[0]["teased"] == 1
