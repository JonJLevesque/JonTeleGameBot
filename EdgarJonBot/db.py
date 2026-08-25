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
        CREATE TABLE IF NOT EXISTS ducks (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            transcript TEXT NOT NULL, PRIMARY KEY (chat_id, user_id)
        );
    """)


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

def add_fact(chat_id, text, source) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO facts (chat_id, text, source, ts) VALUES (?, ?, ?, ?)",
            (chat_id, text, source, time.time()),
        )


def facts(chat_id, limit=200) -> list[sqlite3.Row]:
    return _db().execute(
        "SELECT * FROM facts WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit)
    ).fetchall()


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
