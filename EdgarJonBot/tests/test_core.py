import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")

import db  # noqa: E402
from handlers import reminders  # noqa: E402


def setup_module(module):
    db.init(":memory:")


def test_messages_and_processing():
    for i in range(5):
        n = db.log_message(1, 10, "Jon", f"msg {i}")
    assert n == 5
    rows = db.unprocessed_messages(1)
    assert [r["text"] for r in rows] == [f"msg {i}" for i in range(5)]
    db.mark_processed([r["id"] for r in rows])
    assert db.unprocessed_messages(1) == []
    assert db.chats_with_unprocessed(1) == []


def test_ideas_lifecycle():
    iid = db.add_idea(1, "build a bot", "Jon", "command")
    assert [r["id"] for r in db.ideas(1)] == [iid]
    assert db.set_idea_done(1, iid)
    assert db.ideas(1) == []
    assert not db.delete_idea(2, iid)  # wrong chat
    assert db.delete_idea(1, iid)


def test_facts_relevance():
    db.add_fact(1, "Edgar uses Postgres for the ledger project", "overheard")
    db.add_fact(1, "Jon hates Tailwind", "command")
    assert db.relevant_facts(1, "how is the postgres thing?")[0].startswith("Edgar")
    assert len(db.relevant_facts(1)) == 2


def test_reminders():
    due = time.time() + 60
    rid = db.add_reminder(1, 10, "Jon", "push", due)
    assert [r["id"] for r in db.pending_reminders(1)] == [rid]
    assert db.cancel_reminder(1, rid)
    assert db.pending_reminders(1) == []


def test_quick_parse():
    due, text = reminders._quick_parse("in 2h push the fix")
    assert abs(due - (time.time() + 7200)) < 2 and text == "push the fix"
    assert reminders._quick_parse("tomorrow 9am call Edgar") is None
    assert reminders._quick_parse("in 5m") is None
