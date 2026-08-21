"""Birthday watcher gating: fires once, reminds 3 days out, wraps years."""
from datetime import datetime

from handlers.birthday import check


def _row(month, day, celebrated=0, reminded=0):
    return {"month": month, "day": day,
            "celebrated_year": celebrated, "reminded_year": reminded}


def test_celebrates_on_the_day_once():
    now = datetime(2026, 11, 12, 0, 5)
    assert check(_row(11, 12), now) == "celebrate"
    assert check(_row(11, 12, celebrated=2026), now) is None
    assert check(_row(11, 12, celebrated=2025), now) == "celebrate"


def test_celebrates_all_day_not_just_midnight():
    assert check(_row(11, 12), datetime(2026, 11, 12, 23, 50)) == "celebrate"


def test_reminds_three_days_ahead_once():
    now = datetime(2026, 11, 9, 12, 0)
    assert check(_row(11, 12), now) == "remind"
    assert check(_row(11, 12, reminded=2026), now) is None


def test_reminder_wraps_year_boundary():
    # Jan 2 birthday -> reminder lands Dec 30 of the PREVIOUS year and is
    # gated by the birthday's year (2027), not the reminder's (2026).
    now = datetime(2026, 12, 30, 9, 0)
    assert check(_row(1, 2), now) == "remind"
    assert check(_row(1, 2, reminded=2027), now) is None


def test_quiet_on_ordinary_days():
    row = _row(11, 12)
    for d in (datetime(2026, 11, 8), datetime(2026, 11, 10),
              datetime(2026, 11, 13), datetime(2026, 6, 12)):
        assert check(row, d) is None


def test_dec_birthday_gates():
    assert check(_row(12, 6), datetime(2026, 12, 3, 8, 0)) == "remind"
    assert check(_row(12, 6), datetime(2026, 12, 6, 0, 1)) == "celebrate"


def test_db_round_trip(db):
    db.set_birthday(7, "cherry", 11, 12, "Asia/Kolkata")
    db.set_birthday(8, "Jon", 12, 6, "America/Los_Angeles")
    rows = {b["user_id"]: b for b in db.birthdays_all()}
    assert rows[7]["tz"] == "Asia/Kolkata" and rows[8]["day"] == 6
    db.mark_birthday(7, "celebrated_year", 2026)
    assert db.get_birthday(7)["celebrated_year"] == 2026
    db.set_birthday(7, "cherry", 11, 13, "Asia/Kolkata")  # update keeps row
    assert db.get_birthday(7)["day"] == 13
