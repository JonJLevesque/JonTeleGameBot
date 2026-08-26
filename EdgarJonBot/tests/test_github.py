import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
import github as gh  # noqa: E402
import db  # noqa: E402


def _ev(i, type_, payload, actor="edgar", repo="jon/ledger"):
    return {"id": str(i), "type": type_, "actor": {"login": actor}, "repo": {"name": repo}, "payload": payload}


def test_format_events():
    push = _ev(1, "PushEvent", {"ref": "refs/heads/main", "head": "abcdef1234", "commits": [{"message": "fix: thing\nbody"}, {"message": "second"}]})
    h, p = gh.format_event(push)
    assert "pushed to" in h and "ledger:main" in h and "(+1 more)" in h and "abcdef1" in h
    merged = _ev(2, "PullRequestEvent", {"action": "closed", "pull_request": {"number": 7, "title": "Add <b>", "merged": True, "html_url": "u", "user": {"login": "edgar"}}})
    assert "merged PR" in gh.format_event(merged)[0] and "&lt;b&gt;" in gh.format_event(merged)[0]
    assert gh.merged_pr(merged)["number"] == 7
    assert gh.merged_pr(push) is None
    assert gh.format_event(_ev(3, "WatchEvent", {})) is None
    assert gh.format_event(_ev(4, "PushEvent", {"ref": "refs/heads/x", "commits": []})) is None
    assert "failing" not in gh.format_event(_ev(5, "IssuesEvent", {"action": "opened", "issue": {"number": 1, "title": "bug", "html_url": "u"}}))[0]


def test_new_events_orders_and_filters():
    evs = [_ev(30, "WatchEvent", {}), _ev(10, "WatchEvent", {}), _ev(20, "WatchEvent", {})]
    assert [e["id"] for e in gh.new_events(evs, "10")] == ["20", "30"]
    assert [e["id"] for e in gh.new_events(evs, None)] == ["10", "20", "30"]


def test_parse_repo():
    assert gh.parse_repo("https://github.com/JonJLevesque/JonTeleGameBot.git") == "jonjlevesque/jontelegamebot"
    assert gh.parse_repo("a/b/c") is None
    assert gh.parse_repo("nope") is None


def test_db_watch_state_and_links():
    db.init(":memory:")
    assert db.gh_watch(1, "Jon/Ledger", "J") and not db.gh_watch(1, "jon/ledger", "J")
    assert [r["repo"] for r in db.gh_watched(1)] == ["jon/ledger"]
    db.gh_set("jon/ledger", "last_id", 42)
    assert db.gh_get("jon/ledger", "last_id") == "42"
    db.gh_link(1, 5, "Edgar", "EdgarDev")
    assert db.gh_user_for_login(1, "edgardev")["user_id"] == 5
    for i in range(45):
        db.gh_log_activity(1, f"line {i}")
    assert len(db.gh_recent_activity(1, limit=100)) == 40
    assert db.gh_unwatch(1, "jon/ledger")
