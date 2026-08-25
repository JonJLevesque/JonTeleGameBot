"""Whisper (/tell) persistence and recipient resolution."""
from tests.conftest import FakeUser


def _seed(db):
    # chat -1: jon + cass; chat -2: jon + zoe; chat -3: stranger only
    db.remember_user(-1, FakeUser(1, "Jon"))
    db.remember_user(-1, FakeUser(2, "Cass"))
    db.remember_user(-2, FakeUser(1, "Jon"))
    db.remember_user(-2, FakeUser(3, "Zoe"))
    db.remember_user(-3, FakeUser(4, "Stranger"))


def test_whisper_lifecycle(db):
    wid = db.create_whisper(2, "Cass", 1, "Jon", "you were right")
    pending = db.pending_whispers(1)
    assert [w["id"] for w in pending] == [wid]
    assert pending[0]["message"] == "you were right"
    assert pending[0]["sender_name"] == "Cass"
    db.mark_whisper_delivered(wid)
    assert db.pending_whispers(1) == []


def test_pending_ordered_oldest_first(db):
    a = db.create_whisper(2, "Cass", 1, "Jon", "first")
    b = db.create_whisper(3, "Zoe", 1, "Jon", "second")
    assert [w["id"] for w in db.pending_whispers(1)] == [a, b]


def test_resolve_by_name_and_username(db):
    _seed(db)
    assert db.resolve_recipient(1, "cass") == [(2, "Cass")]
    assert db.resolve_recipient(1, "@zoe") == [(3, "Zoe")]


def test_resolve_only_within_shared_chats(db):
    _seed(db)
    # Stranger shares no chat with Jon; Zoe shares no chat with Cass
    assert db.resolve_recipient(1, "Stranger") == []
    assert db.resolve_recipient(2, "Zoe") == []


def test_resolve_excludes_sender_and_dedupes(db):
    _seed(db)
    assert db.resolve_recipient(1, "Jon") == []  # never yourself
    # Jon is in two chats with Cass-adjacent members; resolving him from
    # Cass's side must yield one row, not one per shared chat.
    db.remember_user(-2, FakeUser(2, "Cass"))
    assert db.resolve_recipient(2, "Jon") == [(1, "Jon")]


def test_shared_chats(db):
    _seed(db)
    assert db.shared_chats(1, 2) == [-1]
    assert db.shared_chats(1, 4) == []
