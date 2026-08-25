"""IOU ledger: creation, settlement rules, nudge cooldown, shop debtor logic."""
import handlers.iou as iou
from handlers.shop import debtor_for

T0 = 1_700_000_000.0


def test_ledger_round_trip_and_settle(db):
    i = db.iou_add(1, 2, "Cherry", 1, "J", "a back rub", "manual", T0)
    assert [r["id"] for r in db.iou_open(1)] == [i]
    assert db.iou_open(2) == []
    assert db.iou_settle(1, i, 2, T0 + 10)
    assert not db.iou_settle(1, i, 2, T0 + 20)      # already settled
    assert db.iou_open(1) == []
    assert db.iou_settled_since(1, T0) == 1
    assert db.iou_settled_since(1, T0 + 11) == 0


def test_cancel_only_open(db):
    i = db.iou_add(1, 2, "Cherry", 1, "J", "dinner", "manual", T0)
    assert db.iou_delete(1, i)
    assert not db.iou_delete(1, i)


def test_nudge_cooldown(db):
    i = db.iou_add(1, 2, "Cherry", 1, "J", "dinner", "manual", T0)
    assert db.iou_nudge(1, i, T0, iou.NUDGE_COOLDOWN)
    assert not db.iou_nudge(1, i, T0 + 60, iou.NUDGE_COOLDOWN)
    assert db.iou_nudge(1, i, T0 + iou.NUDGE_COOLDOWN, iou.NUDGE_COOLDOWN)


def test_ledger_text_groups_by_debtor(db):
    db.iou_add(1, 2, "Cherry", 1, "J", "a coffee", "manual", T0)
    db.iou_add(1, 2, "Cherry", 1, "J", "dinner", "shop", T0 - 20 * 86400)
    db.iou_add(1, 1, "J", 2, "Cherry", "a song", "manual", T0)
    text = iou.ledger_text(db.iou_open(1), T0)
    assert text.count("owes:") == 2
    assert "⏳" in text                       # the 20-day-old one is stale
    assert "20 days" in text
    assert iou.ledger_text([], T0).startswith("🧾 No open IOUs")


def test_shop_add_records_owner_and_debtor_rules(db):
    item_id = db.shop_add(1, 50, "loser cooks dinner", 7, "Cherry")
    item = db.shop_get(1, item_id)
    assert (item["owner_id"], item["owner_name"]) == (7, "Cherry")
    assert debtor_for(item, buyer_id=1, chat_id=1, duo=False) == (7, "Cherry")
    # the owner buying their own reward: in a duo the other person delivers
    from tests.conftest import FakeUser
    db.remember_user(1, FakeUser(1, "J"))
    db.remember_user(1, FakeUser(7, "Cherry"))
    assert debtor_for(item, buyer_id=7, chat_id=1, duo=True) == (1, "J")
    assert debtor_for(item, buyer_id=7, chat_id=1, duo=False) == (None, "the chat")
    legacy = db.shop_get(1, db.shop_add(1, 10, "old reward"))
    assert debtor_for(legacy, buyer_id=7, chat_id=1, duo=False) == (None, "the chat")


def test_age_text():
    assert iou.age_text(T0, T0 + 3600) == "today"
    assert iou.age_text(T0, T0 + 86400) == "1 day"
    assert iou.age_text(T0, T0 + 5 * 86400) == "5 days"
    assert iou.age_text(T0, T0 + 65 * 86400) == "2 mo"


def test_recap_mentions_ious(db):
    from handlers import recap
    db.iou_add(1, 2, "Cherry", 1, "J", "a coffee", "manual", T0)
    text = recap._build(1)
    assert "IOUs: 1 open" in text and "Cherry owes a coffee" in text
