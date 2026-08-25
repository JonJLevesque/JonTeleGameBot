import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")

import db  # noqa: E402
from handlers import brain  # noqa: E402


def setup_function(fn):
    db.init(":memory:")


def test_parse_instruction():
    p = brain.parse_instruction
    assert p("remember Edgar uses Postgres") == ("remember", "Edgar uses Postgres")
    assert p("remember when we broke prod?") is None
    assert p("forget the postgres thing") == ("forget", "postgres thing")
    assert p("erase what you know about the ledger") == ("forget", "the ledger")
    assert p("forget that") == ("forget_last", "")
    assert p("wipe your brain") == ("forget_all", "")
    assert p("delete facts 3/4/5") == ("forget_ids", "3 4 5")
    assert p("what do you know?") is None


def test_remember_and_style_detection():
    text, _ = brain.handle_instruction(1, 9, "remember", "Jon hates Tailwind")
    assert text == "Noted."
    text, _ = brain.handle_instruction(1, 9, "remember", "from now on, keep replies under three lines")
    assert "behave" in text
    assert db.style_notes(1) == ["from now on, keep replies under three lines"]
    assert brain.handle_instruction(1, 9, "remember", "jon hates tailwind")[0] == "Already have that."


def test_forget_variants():
    a = db.add_fact(1, "Edgar moved the ledger to Postgres", "told")
    b = db.add_fact(1, "Edgar's ledger runs on branch wip/pg", "told")
    db.add_fact(1, "Jon hates Tailwind", "told")
    text, kb = brain.handle_forget(1, 9, "forget", "the ledger")
    assert "matches 2" in text and len(kb.inline_keyboard) == 3
    text, kb = brain.handle_forget(1, 9, "forget", "everything about the ledger")
    assert "all 2" in text and kb is None
    assert [r["text"] for r in db.facts(1)] == ["Jon hates Tailwind"]
    text, kb = brain.handle_forget(1, 9, "forget_all", "")
    assert "Wipe all 1" in text and kb is not None and len(db.facts(1)) == 1
    assert "Forgotten" in brain.handle_forget(1, 9, "forget_last", "")[0]
    assert db.facts(1) == []
    assert "None of those" in brain.handle_forget(1, 9, "forget_ids", f"{a} {b}")[0]


def test_apply_learning_replaces_removes_and_files_ideas():
    a = db.add_fact(1, "Edgar is at the mall", "overheard")
    b = db.add_fact(1, "Jon likes Rust", "told")
    db.add_idea(1, "build a commit roaster", "Jon", "command")
    out = brain.apply_learning(1, {
        "facts": ["Jon plays Wordle daily", "edgar is home from the mall"],
        "replace": [{"id": a, "text": "Edgar is home from the mall"}, {"id": 999, "text": "x"}],
        "remove": [b, 999],
        "style": ["Keep replies under three lines"],
        "ideas": ["Build a commit roaster", "a bot that grades PR titles"],
    }, "told", "Jon")
    assert out == (2, 1, 1, 1)
    assert sorted(r["text"] for r in db.facts(1)) == ["Edgar is home from the mall", "Jon plays Wordle daily", "Keep replies under three lines"]
    assert db.style_notes(1) == ["Keep replies under three lines"]
    assert len(db.ideas(1)) == 2
