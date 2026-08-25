"""Persona decision logic: addressing, interjection gate, rate limits."""
import asyncio
import random

import ai
import config
from handlers.persona import (
    CANNED_BUTLER, CANNED_WARM, DAILY_CAP, INTERJECT_AFTER, RateLimiter,
    canned_line, is_addressed, is_operator, should_interject,
)


def test_addressed_by_reply_and_mention():
    assert is_addressed("anything", True, "partybot")
    assert is_addressed("oi @PartyBot settle this", False, "partybot")
    assert not is_addressed("just chatting about bots", False, "partybot")
    assert not is_addressed("", False, "partybot")


def test_interject_needs_ai_quiet_stretch_and_luck():
    assert should_interject(INTERJECT_AFTER, 0.0, True)
    assert not should_interject(INTERJECT_AFTER - 1, 0.0, True)   # too soon
    assert not should_interject(INTERJECT_AFTER, 0.999, True)     # bad roll
    assert not should_interject(INTERJECT_AFTER, 0.0, False)      # no AI


def test_rate_limiter_cooldown():
    rl = RateLimiter(cooldown=15, cap=100)
    assert rl.allow(1, now=100.0, today="2026-08-20")
    rl.record(1, 100.0, "2026-08-20")
    assert not rl.allow(1, 110.0, "2026-08-20")   # inside cooldown
    assert rl.allow(1, 116.0, "2026-08-20")       # cooldown passed
    assert rl.allow(2, 110.0, "2026-08-20")       # other chat unaffected


def test_rate_limiter_daily_cap_and_reset():
    rl = RateLimiter(cooldown=0, cap=3)
    for i in range(3):
        assert rl.allow(1, float(i * 100), "2026-08-20")
        rl.record(1, float(i * 100), "2026-08-20")
    assert not rl.allow(1, 1000.0, "2026-08-20")  # cap hit
    assert rl.allow(1, 2000.0, "2026-08-21")      # new day resets
    assert rl.allow(2, 1000.0, "2026-08-20")      # per-chat cap


def test_canned_bank_shape():
    for bank in (CANNED_WARM, CANNED_BUTLER):
        assert len(bank) >= 8
        assert all(isinstance(line, str) and line for line in bank)
    assert not set(CANNED_WARM) & set(CANNED_BUTLER)
    assert DAILY_CAP > 0


def test_operator_detection(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", 42)
    assert is_operator(42)
    assert not is_operator(7)
    monkeypatch.setattr(config, "ADMIN_ID", 0)
    assert not is_operator(42)  # unset: nobody is the operator


def test_canned_bank_selection():
    rng = random.Random(1)
    assert all(canned_line(True, rng) in CANNED_BUTLER for _ in range(20))
    assert all(canned_line(False, rng) in CANNED_WARM for _ in range(20))


def test_converse_none_without_key(monkeypatch):
    monkeypatch.setattr(ai, "ENABLED", False)
    result = asyncio.run(
        ai.converse(1, user_name="J", text="hello bird")
    )
    assert result is None
