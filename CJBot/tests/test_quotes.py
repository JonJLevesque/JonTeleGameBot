"""Quote wall persistence: save, dedupe, and random retrieval filters."""


def test_save_and_count(db):
    qid = db.save_quote(-1, 100, 2, "Cass", "it me", 1, "Jon")
    assert qid is not None
    assert db.quote_count(-1) == 1
    assert db.quote_count(-2) == 0  # scoped per chat


def test_duplicate_message_returns_none(db):
    assert db.save_quote(-1, 100, 2, "Cass", "it me", 1, "Jon") is not None
    assert db.save_quote(-1, 100, 2, "Cass", "it me", 1, "Jon") is None
    assert db.quote_count(-1) == 1
    # same message_id in a DIFFERENT chat is fine
    assert db.save_quote(-2, 100, 2, "Cass", "it me", 1, "Jon") is not None


def test_null_message_ids_do_not_collide(db):
    # SQLite UNIQUE treats NULLs as distinct: both saves must succeed
    assert db.save_quote(-1, None, 2, "Cass", "one", 1, "Jon") is not None
    assert db.save_quote(-1, None, 2, "Cass", "two", 1, "Jon") is not None
    assert db.quote_count(-1) == 2


def test_random_quote_like_filter(db):
    db.save_quote(-1, 1, 2, "Cass", "pineapple belongs on pizza", 1, "Jon")
    db.save_quote(-1, 2, 1, "Jon", "chess is just spicy checkers", 2, "Cass")
    row = db.random_quote(-1, like="pizza")
    assert row["author_name"] == "Cass"
    assert db.random_quote(-1, like="kayak") is None
    assert db.random_quote(-1) is not None  # unfiltered finds something


def test_random_quote_since_filter(db):
    db.save_quote(-1, 1, 2, "Cass", "old news", 1, "Jon")
    # everything was stamped "now", so a filter in the future finds nothing
    assert db.random_quote(-1, since_ts="2999-01-01 00:00:00") is None
    assert db.random_quote(-1, since_ts="2000-01-01 00:00:00") is not None
