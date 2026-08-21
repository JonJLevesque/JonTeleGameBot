"""Memory system: storage hygiene, instruction parsing, marker stripping."""
from handlers.brain import handle_instruction, parse_instruction, strip_markers


def test_add_and_list(db):
    a = db.add_memory(-1, "cherry hates olives", "told")
    b = db.add_memory(-1, "the car is named the beast", "observed")
    rows = db.memories_all(-1)
    assert [r["id"] for r in rows] == [a, b]
    assert rows[0]["source"] == "told"
    assert db.memories_all(-2) == []


def test_duplicates_and_whitespace_normalized(db):
    db.add_memory(-1, "cherry  hates\nolives", "told")
    assert db.add_memory(-1, "Cherry hates olives", "observed") is None
    assert len(db.memories_all(-1)) == 1


def test_cap_evicts_oldest(db):
    for i in range(db.MEMORY_CAP + 10):
        db.add_memory(-1, f"fact number {i}", "observed")
    rows = db.memories_all(-1)
    assert len(rows) == db.MEMORY_CAP
    assert rows[0]["text"] == "fact number 10"


def test_delete_and_find(db):
    a = db.add_memory(-1, "cherry hates olives", "told")
    db.add_memory(-1, "jon burns toast", "told")
    assert len(db.find_memories(-1, "olives")) == 1
    assert db.delete_memory(-1, a)
    assert not db.delete_memory(-1, a)
    assert db.find_memories(-1, "olives") == []


def test_relevant_memories_keyword_first(db):
    for i in range(40):
        db.add_memory(-1, f"filler fact {i}", "observed")
    db.add_memory(-1, "cherry hates olives", "told")
    out = db.relevant_memories(-1, "should we get olives on the pizza?", limit=5)
    assert out[0] == "cherry hates olives"
    assert len(out) == 5


def test_parse_instruction():
    assert parse_instruction("remember cherry hates olives") == \
        ("remember", "cherry hates olives")
    assert parse_instruction("Please remember: the wifi password is taped to the router") == \
        ("remember", "the wifi password is taped to the router")
    assert parse_instruction("forget the olive thing") == \
        ("forget", "the olive thing")
    # reminiscing, not an instruction
    assert parse_instruction("remember when we went to the lake?") is None
    assert parse_instruction("what do you remember about us?") is None


def test_handle_instruction_roundtrip(db):
    assert "filed" in handle_instruction(-1, "remember", "cherry hates olives")
    assert "Already" in handle_instruction(-1, "remember", "cherry hates olives")
    assert "Forgotten" in handle_instruction(-1, "forget", "olive")
    assert db.memories_all(-1) == []
    assert "Nothing" in handle_instruction(-1, "forget", "olive")


def test_forget_ambiguity(db):
    db.add_memory(-1, "cherry hates olives", "told")
    db.add_memory(-1, "olive oil goes on everything", "told")
    out = handle_instruction(-1, "forget", "olive")
    assert "matches 2" in out
    assert len(db.memories_all(-1)) == 2


def test_strip_markers():
    clean, facts = strip_markers(
        "Noted, I'll keep the calendar clear. "
        "[[remember: cherry's mom visits Friday]] [[remember: jon owes a date night]]"
    )
    assert clean == "Noted, I'll keep the calendar clear."
    assert facts == ["cherry's mom visits Friday", "jon owes a date night"]


def test_strip_markers_caps_at_two_and_handles_none():
    _, facts = strip_markers("a [[remember: 1]] [[remember: 2]] [[remember: 3]]")
    assert facts == ["1", "2"]
    clean, facts = strip_markers("just a normal reply")
    assert clean == "just a normal reply" and facts == []
