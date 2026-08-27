"""Memory system: storage hygiene, instruction parsing, marker stripping."""
from handlers.brain import handle_instruction, parse_instruction, strip_markers


def test_add_and_list(db):
    a = db.add_memory(-1, "audrey hates olives", "told")
    b = db.add_memory(-1, "the car is named the beast", "observed")
    rows = db.memories_all(-1)
    assert [r["id"] for r in rows] == [a, b]
    assert rows[0]["source"] == "told"
    assert db.memories_all(-2) == []


def test_duplicates_and_whitespace_normalized(db):
    db.add_memory(-1, "audrey  hates\nolives", "told")
    assert db.add_memory(-1, "Audrey hates olives", "observed") is None
    assert len(db.memories_all(-1)) == 1


def test_cap_evicts_oldest(db):
    for i in range(db.MEMORY_CAP + 10):
        db.add_memory(-1, f"fact number {i}", "observed")
    rows = db.memories_all(-1)
    assert len(rows) == db.MEMORY_CAP
    assert rows[0]["text"] == "fact number 10"


def test_delete_and_find(db):
    a = db.add_memory(-1, "audrey hates olives", "told")
    db.add_memory(-1, "jon burns toast", "told")
    assert len(db.find_memories(-1, "olives")) == 1
    assert db.delete_memory(-1, a)
    assert not db.delete_memory(-1, a)
    assert db.find_memories(-1, "olives") == []


def test_relevant_memories_keyword_first(db):
    for i in range(40):
        db.add_memory(-1, f"filler fact {i}", "observed")
    db.add_memory(-1, "audrey hates olives", "told")
    out = db.relevant_memories(-1, "should we get olives on the pizza?", limit=5)
    assert out[0] == "audrey hates olives"
    assert len(out) == 5


def test_parse_instruction():
    assert parse_instruction("remember audrey hates olives") == \
        ("remember", "audrey hates olives")
    assert parse_instruction("Please remember: the wifi password is taped to the router") == \
        ("remember", "the wifi password is taped to the router")
    assert parse_instruction("forget the olive thing") == \
        ("forget", "olive thing")
    # reminiscing, not an instruction
    assert parse_instruction("remember when we went to the lake?") is None
    assert parse_instruction("what do you remember about us?") is None


def test_handle_instruction_roundtrip(db):
    assert "filed" in handle_instruction(-1, "remember", "audrey hates olives")
    assert "Already" in handle_instruction(-1, "remember", "audrey hates olives")
    assert "Forgotten" in handle_instruction(-1, "forget", "olive")
    assert db.memories_all(-1) == []
    assert "Nothing" in handle_instruction(-1, "forget", "olive")


def test_forget_ambiguity(db):
    db.add_memory(-1, "audrey hates olives", "told")
    db.add_memory(-1, "olive oil goes on everything", "told")
    out = handle_instruction(-1, "forget", "olive")
    assert "matches 2" in out
    assert len(db.memories_all(-1)) == 2


def test_strip_markers():
    clean, facts = strip_markers(
        "Noted, I'll keep the calendar clear. "
        "[[remember: audrey's mom visits Friday]] [[remember: jon owes a date night]]"
    )
    assert clean == "Noted, I'll keep the calendar clear."
    assert facts == ["audrey's mom visits Friday", "jon owes a date night"]


def test_strip_markers_caps_at_two_and_handles_none():
    _, facts = strip_markers("a [[remember: 1]] [[remember: 2]] [[remember: 3]]")
    assert facts == ["1", "2"]
    clean, facts = strip_markers("just a normal reply")
    assert clean == "just a normal reply" and facts == []


# --------------------------------------------------- natural-language forgetting
from handlers.brain import handle_forget  # noqa: E402


def test_parse_forget_phrasings():
    assert parse_instruction("erase the memory about the mall") == ("forget", "the mall")
    assert parse_instruction("Delete what you know about grandma") == ("forget", "grandma")
    assert parse_instruction("stop remembering the olive thing") == ("forget", "olive thing")
    assert parse_instruction("wipe your memory") == ("forget_all", "")
    assert parse_instruction("forget everything") == ("forget_all", "")
    assert parse_instruction("forget everything you know about us") == ("forget_all", "")
    assert parse_instruction("forget what I just said") == ("forget_last", "")
    assert parse_instruction("forget that") == ("forget_last", "")
    assert parse_instruction("delete memories 7/13/14/15") == ("forget_ids", "7 13 14 15")
    assert parse_instruction("forget #7, #13 and 14") == ("forget_ids", "7 13 14")
    assert parse_instruction("forget everything about the mall") == ("forget", "everything about the mall")


def test_forget_by_words_and_scope(db):
    db.add_memory(-1, "J is at the mall with grandma", "told")
    db.add_memory(-1, "J corrected the mall info", "told")
    db.add_memory(-1, "audrey hates olives", "told")
    text, kb = handle_forget(-1, 9, "forget", "the mall")
    assert "matches 2" in text and kb is not None
    assert len(kb.inline_keyboard) == 3                      # two picks + "all of these"
    assert all(b.callback_data.startswith("mem:9:") for row in kb.inline_keyboard for b in row)
    text, kb = handle_forget(-1, 9, "forget", "everything about the mall")
    assert "all 2" in text and kb is None
    assert [r["text"] for r in db.memories_all(-1)] == ["audrey hates olives"]


def test_forget_ids_last_and_all(db):
    a = db.add_memory(-1, "one", "told")
    b = db.add_memory(-1, "two", "told")
    c = db.add_memory(-1, "three", "told")
    text, _ = handle_forget(-1, 9, "forget_ids", f"{a} {b} 999")
    assert "Forgotten 2" in text and "999" in text
    text, _ = handle_forget(-1, 9, "forget_last", "")
    assert "three" in text and db.memories_all(-1) == []
    assert "empty" in handle_forget(-1, 9, "forget_all", "")[0]
    db.add_memory(-1, "x", "told")
    text, kb = handle_forget(-1, 9, "forget_all", "")
    assert "Wipe all 1" in text and kb.inline_keyboard[0][0].callback_data == "mem:9:wipe:"
    assert len(db.memories_all(-1)) == 1                     # nothing deleted until confirmed
    assert db.delete_all_memories(-1) == 1


# ------------------------------------------------------------ active learning
import ai as _ai  # noqa: E402
from handlers.brain import apply_learning  # noqa: E402


def test_parse_learning_tolerates_prose_and_junk():
    assert _ai.parse_learning('Sure! {"add": ["J plays Wordle daily"], "replace": [{"id": 3, "text": "J is home"}], "remove": [7, "x"]}') == \
        {"add": ["J plays Wordle daily"], "replace": [{"id": 3, "text": "J is home"}], "remove": [7]}
    assert _ai.parse_learning("") is None
    assert _ai.parse_learning("no json here") is None
    assert _ai.parse_learning('{"add": []}') == {"add": [], "replace": [], "remove": []}


def test_apply_learning_replaces_and_removes(db):
    a = db.add_memory(-1, "J is at the mall with grandma", "observed")
    b = db.add_memory(-1, "audrey hates olives", "told")
    added, replaced, removed = apply_learning(-1, {
        "add": ["J plays Wordle daily", "J is home from the mall"],   # second dups the replacement
        "replace": [{"id": a, "text": "J is home from the mall"}, {"id": 999, "text": "ghost"}],
        "remove": [b, 999],
    }, "told")
    assert (added, replaced, removed) == (1, 1, 1)
    assert sorted(r["text"] for r in db.memories_all(-1)) == ["J is home from the mall", "J plays Wordle daily"]
