"""SQLite persistence. WAL mode; calls are sync but microsecond-cheap."""
import glob
import os
import sqlite3
import time

_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    assert _conn is not None, "db.init() first"
    return _conn


def init(path: str) -> None:
    global _conn
    _conn = sqlite3.connect(path, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            username TEXT, first_name TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            name TEXT NOT NULL, text TEXT NOT NULL,
            ts REAL NOT NULL, processed INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS messages_chat ON messages (chat_id, id);
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, text TEXT NOT NULL,
            by_name TEXT NOT NULL, source TEXT NOT NULL,   -- 'command' | 'overheard'
            ts REAL NOT NULL, done INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS shipped (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            name TEXT NOT NULL, text TEXT NOT NULL, ts REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, text TEXT NOT NULL,
            source TEXT NOT NULL, ts REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            name TEXT NOT NULL, text TEXT NOT NULL,
            due REAL NOT NULL, fired INTEGER NOT NULL DEFAULT 0
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            text, content='messages', content_rowid='id', tokenize='porter unicode61'
        );
        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text);
        END;
        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.id, old.text);
        END;
        CREATE TABLE IF NOT EXISTS journal (
            chat_id INTEGER NOT NULL, day TEXT NOT NULL, summary TEXT NOT NULL,
            messages INTEGER NOT NULL DEFAULT 0, ts REAL NOT NULL,
            PRIMARY KEY (chat_id, day)
        );
        CREATE TABLE IF NOT EXISTS gh_watch (
            chat_id INTEGER NOT NULL, repo TEXT NOT NULL, added_by TEXT NOT NULL,
            PRIMARY KEY (chat_id, repo)
        );
        CREATE TABLE IF NOT EXISTS gh_state (
            repo TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
            PRIMARY KEY (repo, key)
        );
        CREATE TABLE IF NOT EXISTS gh_users (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, name TEXT NOT NULL, login TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS gh_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL, line TEXT NOT NULL, ts REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ducks (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            transcript TEXT NOT NULL, PRIMARY KEY (chat_id, user_id)
        );
    """)


def _ensure_fts_populated() -> None:
    n = _db().execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    m = _db().execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
    if n and not m:
        rebuild_fts()


def backup(dest_dir: str, keep: int = 14) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"edgarjon-{time.strftime('%Y%m%d-%H%M%S')}.db")
    with sqlite3.connect(dest) as target:
        _db().backup(target)
    for old in sorted(glob.glob(os.path.join(dest_dir, "edgarjon-*.db")))[:-keep]:
        os.remove(old)
    return dest


# ------------------------------------------------------------------ users

def remember_user(chat_id, user) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO users (chat_id, user_id, username, first_name) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (chat_id, user_id) DO UPDATE SET "
            "username = excluded.username, first_name = excluded.first_name",
            (chat_id, user.id, (user.username or "").lower() or None, user.first_name),
        )


def chat_members(chat_id) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM users WHERE chat_id = ? ORDER BY first_name", (chat_id,)
    ).fetchall()


# --------------------------------------------------------------- messages

def log_message(chat_id, user_id, name, text) -> int:
    with _db() as c:
        c.execute(
            "INSERT INTO messages (chat_id, user_id, name, text, ts) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, name, text, time.time()),
        )
    return c.execute(
        "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND processed = 0", (chat_id,)
    ).fetchone()[0]


def recent_messages(chat_id, limit=30) -> list[sqlite3.Row]:
    rows = _db().execute(
        "SELECT * FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    return list(reversed(rows))


def _fts_query(text: str) -> str:
    import re
    words = [w for w in re.findall(r"[a-zA-Z0-9_']{3,}", text) if w.lower() not in _STOP]
    return " OR ".join(f'"{w}"' for w in words[:12])


def search_messages(chat_id, query: str, limit=8, exclude_last=30) -> list[sqlite3.Row]:
    """Older messages relevant to `query`, best match first. Skips the most
    recent `exclude_last` rows (those are already in the prompt)."""
    q = _fts_query(query)
    if not q:
        return []
    cutoff = 2 ** 62
    if exclude_last:
        cutoff = _db().execute(
            "SELECT COALESCE(MIN(id), ?) FROM (SELECT id FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?)",
            (cutoff, chat_id, exclude_last),
        ).fetchone()[0]
    try:
        return _db().execute(
            "SELECT m.* FROM messages_fts f JOIN messages m ON m.id = f.rowid "
            "WHERE messages_fts MATCH ? AND m.chat_id = ? AND m.id < ? ORDER BY bm25(messages_fts) LIMIT ?",
            (q, chat_id, cutoff, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def messages_between(chat_id, start_ts, end_ts) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM messages WHERE chat_id = ? AND ts >= ? AND ts < ? ORDER BY id",
        (chat_id, start_ts, end_ts),
    ).fetchall()


def rebuild_fts() -> None:
    with _db() as c:
        c.execute("INSERT INTO messages_fts(messages_fts) VALUES ('rebuild')")


def journal_put(chat_id, day, summary, messages) -> None:
    with _db() as c:
        c.execute("INSERT INTO journal (chat_id, day, summary, messages, ts) VALUES (?, ?, ?, ?, ?) "
                  "ON CONFLICT (chat_id, day) DO UPDATE SET summary = excluded.summary, messages = excluded.messages, ts = excluded.ts",
                  (chat_id, day, summary[:1500], messages, time.time()))


def journal_get(chat_id, day):
    return _db().execute("SELECT * FROM journal WHERE chat_id = ? AND day = ?", (chat_id, day)).fetchone()


def journal_recent(chat_id, days=7) -> list[sqlite3.Row]:
    rows = _db().execute("SELECT * FROM journal WHERE chat_id = ? ORDER BY day DESC LIMIT ?", (chat_id, days)).fetchall()
    return list(reversed(rows))


def journal_missing_days(chat_id, days: list[str]) -> list[str]:
    have = {r["day"] for r in _db().execute("SELECT day FROM journal WHERE chat_id = ?", (chat_id,)).fetchall()}
    return [d for d in days if d not in have]


def chat_ids_with_messages() -> list[int]:
    return [r[0] for r in _db().execute("SELECT DISTINCT chat_id FROM messages").fetchall()]


def unprocessed_messages(chat_id) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM messages WHERE chat_id = ? AND processed = 0 ORDER BY id",
        (chat_id,),
    ).fetchall()


def mark_processed(ids: list[int]) -> None:
    if not ids:
        return
    with _db() as c:
        c.executemany("UPDATE messages SET processed = 1 WHERE id = ?", [(i,) for i in ids])


def chats_with_unprocessed(min_count: int) -> list[tuple[int, float]]:
    """(chat_id, last message ts) for chats with >= min_count unread messages."""
    return [
        (r[0], r[1]) for r in _db().execute(
            "SELECT chat_id, MAX(ts) FROM messages WHERE processed = 0 "
            "GROUP BY chat_id HAVING COUNT(*) >= ?", (min_count,)
        ).fetchall()
    ]


def messages_since(chat_id, since_ts) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM messages WHERE chat_id = ? AND ts >= ? ORDER BY id",
        (chat_id, since_ts),
    ).fetchall()


# ------------------------------------------------------------------ ideas

def add_idea(chat_id, text, by_name, source) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO ideas (chat_id, text, by_name, source, ts) VALUES (?, ?, ?, ?, ?)",
            (chat_id, text, by_name, source, time.time()),
        )
    return cur.lastrowid


def ideas(chat_id, include_done=False, limit=50) -> list[sqlite3.Row]:
    q = "SELECT * FROM ideas WHERE chat_id = ?" + ("" if include_done else " AND done = 0")
    return _db().execute(q + " ORDER BY id DESC LIMIT ?", (chat_id, limit)).fetchall()


def idea_texts(chat_id) -> list[str]:
    return [r["text"] for r in ideas(chat_id, include_done=True, limit=200)]


def set_idea_done(chat_id, idea_id, done=True) -> bool:
    with _db() as c:
        cur = c.execute(
            "UPDATE ideas SET done = ? WHERE chat_id = ? AND id = ?",
            (1 if done else 0, chat_id, idea_id),
        )
    return cur.rowcount > 0


def delete_idea(chat_id, idea_id) -> bool:
    with _db() as c:
        cur = c.execute("DELETE FROM ideas WHERE chat_id = ? AND id = ?", (chat_id, idea_id))
    return cur.rowcount > 0


# ---------------------------------------------------------------- shipped

def add_shipped(chat_id, user_id, name, text) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO shipped (chat_id, user_id, name, text, ts) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, name, text, time.time()),
        )


def shipped_since(chat_id, since_ts) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM shipped WHERE chat_id = ? AND ts >= ? ORDER BY id",
        (chat_id, since_ts),
    ).fetchall()


def shipped_recent(chat_id, limit=15) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM shipped WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit)
    ).fetchall()


# ------------------------------------------------------------------ facts

def add_fact(chat_id, text, source) -> int | None:
    """Store a fact; near-duplicates (case-insensitive) are skipped."""
    text = " ".join(text.split())[:200]
    if not text:
        return None
    with _db() as c:
        if c.execute("SELECT 1 FROM facts WHERE chat_id = ? AND LOWER(text) = LOWER(?)", (chat_id, text)).fetchone():
            return None
        cur = c.execute(
            "INSERT INTO facts (chat_id, text, source, ts) VALUES (?, ?, ?, ?)",
            (chat_id, text, source, time.time()),
        )
    return cur.lastrowid


def facts(chat_id, limit=200) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM facts WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit)
    ).fetchall()


def replace_fact(chat_id, fact_id, text) -> bool:
    text = " ".join(text.split())[:200]
    if not text:
        return False
    with _db() as c:
        cur = c.execute("UPDATE facts SET text = ? WHERE chat_id = ? AND id = ?", (text, chat_id, fact_id))
    return cur.rowcount > 0


def delete_facts(chat_id, ids: list[int]) -> int:
    if not ids:
        return 0
    marks = ",".join("?" for _ in ids)
    with _db() as c:
        cur = c.execute(f"DELETE FROM facts WHERE chat_id = ? AND id IN ({marks})", (chat_id, *ids))
    return cur.rowcount


def delete_all_facts(chat_id) -> int:
    with _db() as c:
        cur = c.execute("DELETE FROM facts WHERE chat_id = ?", (chat_id,))
    return cur.rowcount


def latest_fact(chat_id):
    return _db().execute("SELECT * FROM facts WHERE chat_id = ? ORDER BY id DESC LIMIT 1", (chat_id,)).fetchone()


_STOP = {"the", "that", "this", "thing", "about", "what", "you", "know", "said",
         "told", "and", "for", "with", "everything", "all", "stuff"}


def find_facts(chat_id, hint: str):
    """Facts mentioning the phrase; else facts containing every significant word."""
    import re
    words = [w for w in re.findall(r"[a-z0-9']+", hint.lower()) if len(w) >= 3 and w not in _STOP]
    phrase = " ".join(words) or hint.strip()
    rows = _db().execute(
        "SELECT * FROM facts WHERE chat_id = ? AND LOWER(text) LIKE ? ORDER BY id", (chat_id, f"%{phrase.lower()}%")
    ).fetchall()
    if not words:
        return rows
    by_words = [r for r in facts(chat_id, limit=500) if all(w in r["text"].lower() for w in words)]
    return by_words if len(by_words) > len(rows) else rows


def style_notes(chat_id) -> list[str]:
    return [r["text"] for r in _db().execute(
        "SELECT text FROM facts WHERE chat_id = ? AND source = 'style' ORDER BY id", (chat_id,)
    ).fetchall()]


def delete_fact(chat_id, fact_id) -> bool:
    with _db() as c:
        cur = c.execute("DELETE FROM facts WHERE chat_id = ? AND id = ?", (chat_id, fact_id))
    return cur.rowcount > 0


def relevant_facts(chat_id, text="", limit=40) -> list[str]:
    rows = facts(chat_id)
    words = {w.strip("?.,!").lower() for w in text.split() if len(w) >= 4}
    hits = [r["text"] for r in rows if words and any(w in r["text"].lower() for w in words)]
    out: list[str] = []
    for t in hits + [r["text"] for r in rows]:
        if t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


# -------------------------------------------------------------- reminders

def add_reminder(chat_id, user_id, name, text, due) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO reminders (chat_id, user_id, name, text, due) VALUES (?, ?, ?, ?, ?)",
            (chat_id, user_id, name, text, due),
        )
    return cur.lastrowid


def pending_reminders(chat_id=None) -> list[sqlite3.Row]:
    q = "SELECT * FROM reminders WHERE fired = 0"
    args: tuple = ()
    if chat_id is not None:
        q += " AND chat_id = ?"
        args = (chat_id,)
    return _db().execute(q + " ORDER BY due", args).fetchall()


def get_reminder(rid) -> sqlite3.Row | None:
    return _db().execute("SELECT * FROM reminders WHERE id = ?", (rid,)).fetchone()


def mark_fired(rid) -> None:
    with _db() as c:
        c.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (rid,))


def cancel_reminder(chat_id, rid) -> bool:
    with _db() as c:
        cur = c.execute(
            "DELETE FROM reminders WHERE chat_id = ? AND id = ? AND fired = 0", (chat_id, rid)
        )
    return cur.rowcount > 0


# ------------------------------------------------------------------ ducks

def get_duck(chat_id, user_id) -> str | None:
    row = _db().execute(
        "SELECT transcript FROM ducks WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
    ).fetchone()
    return row["transcript"] if row else None


def set_duck(chat_id, user_id, transcript: str | None) -> None:
    with _db() as c:
        if transcript is None:
            c.execute("DELETE FROM ducks WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        else:
            c.execute(
                "INSERT INTO ducks (chat_id, user_id, transcript) VALUES (?, ?, ?) "
                "ON CONFLICT (chat_id, user_id) DO UPDATE SET transcript = excluded.transcript",
                (chat_id, user_id, transcript),
            )


# ----------------------------------------------------------------- github

def gh_watch(chat_id, repo, added_by) -> bool:
    with _db() as c:
        cur = c.execute("INSERT OR IGNORE INTO gh_watch (chat_id, repo, added_by) VALUES (?, ?, ?)", (chat_id, repo.lower(), added_by))
    return cur.rowcount > 0


def gh_unwatch(chat_id, repo) -> bool:
    with _db() as c:
        cur = c.execute("DELETE FROM gh_watch WHERE chat_id = ? AND repo = ?", (chat_id, repo.lower()))
    return cur.rowcount > 0


def gh_watched(chat_id=None) -> list[sqlite3.Row]:
    if chat_id is None:
        return _db().execute("SELECT * FROM gh_watch ORDER BY repo").fetchall()
    return _db().execute("SELECT * FROM gh_watch WHERE chat_id = ? ORDER BY repo", (chat_id,)).fetchall()


def gh_get(repo, key, default=None):
    r = _db().execute("SELECT value FROM gh_state WHERE repo = ? AND key = ?", (repo.lower(), key)).fetchone()
    return r["value"] if r else default


def gh_set(repo, key, value) -> None:
    with _db() as c:
        c.execute("INSERT INTO gh_state (repo, key, value) VALUES (?, ?, ?) ON CONFLICT (repo, key) DO UPDATE SET value = excluded.value",
                  (repo.lower(), key, str(value)))


def gh_link(chat_id, user_id, name, login) -> None:
    with _db() as c:
        c.execute("INSERT INTO gh_users (chat_id, user_id, name, login) VALUES (?, ?, ?, ?) "
                  "ON CONFLICT (chat_id, user_id) DO UPDATE SET name = excluded.name, login = excluded.login",
                  (chat_id, user_id, name, login.lower()))


def gh_user_for_login(chat_id, login):
    return _db().execute("SELECT * FROM gh_users WHERE chat_id = ? AND login = ?", (chat_id, login.lower())).fetchone()


def gh_logins(chat_id) -> list[sqlite3.Row]:
    return _db().execute("SELECT * FROM gh_users WHERE chat_id = ?", (chat_id,)).fetchall()


def gh_log_activity(chat_id, line) -> None:
    with _db() as c:
        c.execute("INSERT INTO gh_activity (chat_id, line, ts) VALUES (?, ?, ?)", (chat_id, line[:200], time.time()))
        c.execute("DELETE FROM gh_activity WHERE chat_id = ? AND id NOT IN (SELECT id FROM gh_activity WHERE chat_id = ? ORDER BY id DESC LIMIT 40)", (chat_id, chat_id))


def gh_recent_activity(chat_id, limit=12) -> list[str]:
    rows = _db().execute("SELECT line FROM gh_activity WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit)).fetchall()
    return [r["line"] for r in reversed(rows)]
