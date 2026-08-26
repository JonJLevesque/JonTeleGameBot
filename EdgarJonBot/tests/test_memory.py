import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
import db  # noqa: E402


def setup_function(fn):
    db.init(":memory:")


def test_fts_search_skips_recent_and_ranks():
    for i in range(40):
        db.log_message(1, 1, "Jon", f"filler message number {i}")
    db.log_message(1, 2, "Edgar", "I moved the ledger service to Postgres last night")
    for i in range(30):
        db.log_message(1, 1, "Jon", f"more filler {i}")
    hits = db.search_messages(1, "what happened with the postgres migration?", limit=5, exclude_last=30)
    assert [h["name"] for h in hits] == ["Edgar"]
    assert db.search_messages(1, "the and for", limit=5) == []
    assert db.search_messages(2, "postgres", limit=5) == []


def test_fts_survives_delete_and_rebuild():
    i = db.log_message(1, 1, "Jon", "unique zebra token")
    assert db.search_messages(1, "zebra", exclude_last=0)
    db._db().execute("DELETE FROM messages WHERE id = ?", (i,))
    assert db.search_messages(1, "zebra", exclude_last=0) == []
    db.log_message(1, 1, "Jon", "giraffe token")
    db._db().execute("DELETE FROM messages_fts WHERE rowid IN (SELECT rowid FROM messages_fts)")
    db.rebuild_fts()
    assert db.search_messages(1, "giraffe", exclude_last=0)


def test_journal_and_missing_days():
    db.journal_put(1, "2026-08-25", "They argued about tabs.", 12)
    db.journal_put(1, "2026-08-25", "They argued about tabs, then made up.", 14)
    assert db.journal_get(1, "2026-08-25")["messages"] == 14
    assert db.journal_missing_days(1, ["2026-08-24", "2026-08-25"]) == ["2026-08-24"]
    assert [r["day"] for r in db.journal_recent(1)] == ["2026-08-25"]


def test_messages_between_and_chat_ids():
    t = time.time()
    db.log_message(1, 1, "Jon", "a")
    assert len(db.messages_between(1, t - 1, t + 1)) == 1
    assert db.chat_ids_with_messages() == [1]
