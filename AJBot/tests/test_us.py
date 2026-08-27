from handlers.usquiz import parse_quiz
from handlers.places import parse_been


def test_parse_quiz():
    raw = "SUBJECT: Jon\nAudrey: what does Jon insist is the best pizza?\nNeapolitan\n*Detroit-style\nNew York\nChicago"
    assert parse_quiz(raw) == ("Jon", "Audrey: what does Jon insist is the best pizza?", ["Neapolitan", "Detroit-style", "New York", "Chicago"], 1)
    assert parse_quiz("nope") is None
    assert parse_quiz("SUBJECT: Jon\nq\na\nb\nc\nd") is None   # no correct marker


def test_parse_been():
    assert parse_been("Lisbon | the tram ride") == ("Lisbon", "the tram ride")
    assert parse_been("  Big   Sur ") == ("Big Sur", None)


def test_museum_db(db):
    from tests.conftest import FakeUser
    q = db.save_quote(1, 10, 2, "Audrey", "we are not buying a boat", 1, "Jon")
    assert db.museum_wings(1) == [("Uncatalogued", 1)]
    db.quote_set_curation(q, "Nautical Regrets", "Acquired shortly before the boat.")
    assert db.museum_wings(1) == [("Nautical Regrets", 1)]
    assert db.museum_wing(1, "nautical regrets")[0]["plaque"].startswith("Acquired")
    assert db.uncurated_quotes(1) == []
    assert db.place_add(1, "Lisbon", "Lisbon, Portugal", 38.7, -9.1, None, "Jon")
    assert db.place_add(1, "lisbon", "Lisbon, Portugal", 38.7, -9.1, None, "Jon") is None
    assert len(db.places(1)) == 1 and db.place_remove(1, "LISBON")
