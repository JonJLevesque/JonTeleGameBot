"""SQLite persistence layer.

Everything that must survive a restart lives here: cookie balances,
board-game state, paranoia rounds, and the chat-member cache used to
resolve @username mentions (the Bot API cannot look up usernames).

sqlite3 calls are synchronous but each statement is microseconds of work,
so they are called directly from async handlers. WAL mode keeps readers
and the single writer from blocking each other.
"""
import glob
import json
import os
import sqlite3
import time

_conn: sqlite3.Connection | None = None


def backup(dest_dir: str, keep: int = 14) -> str:
    """Consistent online backup via SQLite's backup API; prunes old copies."""
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(
        dest_dir, f"partybot-{time.strftime('%Y%m%d-%H%M%S')}.db"
    )
    with sqlite3.connect(dest) as target:
        _db().backup(target)
    for old in sorted(glob.glob(os.path.join(dest_dir, "partybot-*.db")))[:-keep]:
        os.remove(old)
    return dest


def latest_backup_age_hours(dest_dir: str) -> float | None:
    files = glob.glob(os.path.join(dest_dir, "partybot-*.db"))
    if not files:
        return None
    return (time.time() - max(os.path.getmtime(f) for f in files)) / 3600


def init(path: str) -> None:
    global _conn
    _conn = sqlite3.connect(path, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS known_users (
            chat_id    INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            username   TEXT,            -- lowercase, without '@', may be NULL
            first_name TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS cookies (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            count   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS games (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id    INTEGER NOT NULL,
            message_id INTEGER,
            game_type  TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'pending',  -- pending | active | finished
            p0_id      INTEGER NOT NULL,
            p0_name    TEXT NOT NULL,
            p1_id      INTEGER,                          -- NULL = open challenge
            p1_name    TEXT,
            state      TEXT,                             -- JSON blob owned by the game class
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            spicy   INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS taboo_rounds (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id        INTEGER NOT NULL,
            describer_id   INTEGER NOT NULL,
            describer_name TEXT NOT NULL,
            phrase         TEXT NOT NULL,
            clues_used     INTEGER NOT NULL DEFAULT 0,
            stage          TEXT NOT NULL DEFAULT 'active'  -- active | done
        );
        CREATE INDEX IF NOT EXISTS idx_taboo_active
            ON taboo_rounds (chat_id) WHERE stage = 'active';

        CREATE TABLE IF NOT EXISTS beautiful (
            chat_id INTEGER PRIMARY KEY,
            state   TEXT NOT NULL              -- JSON blob owned by handlers/beautiful.py
        );

        CREATE TABLE IF NOT EXISTS wordle_days (
            day    TEXT PRIMARY KEY,              -- ISO date
            number INTEGER NOT NULL,              -- public puzzle number
            word   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wordle_plays (
            user_id    INTEGER NOT NULL,
            day        TEXT NOT NULL,
            first_name TEXT NOT NULL,
            guesses    TEXT NOT NULL DEFAULT '[]',  -- JSON list of words
            done       INTEGER NOT NULL DEFAULT 0,
            won        INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day)
        );

        CREATE TABLE IF NOT EXISTS wordle_duels (
            chat_id   INTEGER NOT NULL,
            day       TEXT NOT NULL,
            winner_id INTEGER,                    -- NULL = tie
            PRIMARY KEY (chat_id, day)
        );

        CREATE TABLE IF NOT EXISTS dailyq (
            chat_id INTEGER PRIMARY KEY,
            hour    INTEGER NOT NULL,
            minute  INTEGER NOT NULL,
            idx     INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS paranoia_rounds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER NOT NULL,
            target_id   INTEGER NOT NULL,
            target_name TEXT NOT NULL,
            question    TEXT NOT NULL,
            stage       TEXT NOT NULL DEFAULT 'asked'    -- asked | done
        );
        """
    )
    _conn.commit()


def _db() -> sqlite3.Connection:
    assert _conn is not None, "db.init() was not called"
    return _conn


# ---------------------------------------------------------------- known users

def remember_user(chat_id: int, user) -> None:
    """Cache a telegram.User we saw in this chat, for later @username lookup."""
    if user is None or user.is_bot:
        return
    with _db() as c:
        c.execute(
            "INSERT INTO known_users (chat_id, user_id, username, first_name) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (chat_id, user_id) DO UPDATE SET "
            "  username = excluded.username, first_name = excluded.first_name",
            (chat_id, user.id, (user.username or "").lower() or None, user.first_name),
        )


def resolve_username(chat_id: int, username: str):
    """Return (user_id, first_name) for an @username seen before in this chat."""
    row = _db().execute(
        "SELECT user_id, first_name FROM known_users WHERE chat_id = ? AND username = ?",
        (chat_id, username.lstrip("@").lower()),
    ).fetchone()
    return (row["user_id"], row["first_name"]) if row else None


def random_known_users(chat_id: int, exclude_ids: tuple[int, ...], limit: int):
    """Up to `limit` random cached members of the chat, excluding the given ids."""
    marks = ",".join("?" for _ in exclude_ids) or "0"
    rows = _db().execute(
        f"SELECT user_id, first_name FROM known_users "
        f"WHERE chat_id = ? AND user_id NOT IN ({marks}) "
        f"ORDER BY RANDOM() LIMIT ?",
        (chat_id, *exclude_ids, limit),
    ).fetchall()
    return [(r["user_id"], r["first_name"]) for r in rows]


# -------------------------------------------------------------------- cookies

def add_cookies(chat_id: int, user_id: int, delta: int) -> int:
    """Adjust a balance and return the new total."""
    with _db() as c:
        c.execute(
            "INSERT INTO cookies (chat_id, user_id, count) VALUES (?, ?, ?) "
            "ON CONFLICT (chat_id, user_id) DO UPDATE SET count = count + ?",
            (chat_id, user_id, delta, delta),
        )
    return get_cookies(chat_id, user_id)


def get_cookies(chat_id: int, user_id: int) -> int:
    row = _db().execute(
        "SELECT count FROM cookies WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    ).fetchone()
    return row["count"] if row else 0


def cookie_leaderboard(chat_id: int, limit: int = 10):
    """[(first_name, count), ...] top holders in this chat."""
    rows = _db().execute(
        "SELECT k.first_name, c.count FROM cookies c "
        "JOIN known_users k ON k.chat_id = c.chat_id AND k.user_id = c.user_id "
        "WHERE c.chat_id = ? AND c.count > 0 "
        "ORDER BY c.count DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    return [(r["first_name"], r["count"]) for r in rows]


# ---------------------------------------------------------------- board games

def create_game(chat_id, game_type, p0_id, p0_name, p1_id, p1_name) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO games (chat_id, game_type, p0_id, p0_name, p1_id, p1_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, game_type, p0_id, p0_name, p1_id, p1_name),
        )
    return cur.lastrowid


def set_game_message(game_id: int, message_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE games SET message_id = ? WHERE id = ?", (message_id, game_id))


def get_game(game_id: int):
    return _db().execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()


def update_game(game_id: int, *, status=None, state=None, p1_id=None, p1_name=None) -> None:
    sets, args = ["updated_at = datetime('now')"], []
    if status is not None:
        sets.append("status = ?"); args.append(status)
    if state is not None:
        sets.append("state = ?"); args.append(json.dumps(state))
    if p1_id is not None:
        sets.append("p1_id = ?"); args.append(p1_id)
    if p1_name is not None:
        sets.append("p1_name = ?"); args.append(p1_name)
    args.append(game_id)
    with _db() as c:
        c.execute(f"UPDATE games SET {', '.join(sets)} WHERE id = ?", args)


# ------------------------------------------------------------- chat settings

def set_spicy(chat_id: int, enabled: bool) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO chat_settings (chat_id, spicy) VALUES (?, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET spicy = excluded.spicy",
            (chat_id, int(enabled)),
        )


def is_spicy(chat_id: int) -> bool:
    row = _db().execute(
        "SELECT spicy FROM chat_settings WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return bool(row["spicy"]) if row else False


# ---------------------------------------------------------------------- taboo

def create_taboo(chat_id, describer_id, describer_name, phrase) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO taboo_rounds (chat_id, describer_id, describer_name, phrase) "
            "VALUES (?, ?, ?, ?)",
            (chat_id, describer_id, describer_name, phrase),
        )
    return cur.lastrowid


def get_active_taboo(chat_id: int):
    return _db().execute(
        "SELECT * FROM taboo_rounds WHERE chat_id = ? AND stage = 'active' "
        "ORDER BY id DESC LIMIT 1",
        (chat_id,),
    ).fetchone()


def get_taboo(round_id: int):
    return _db().execute(
        "SELECT * FROM taboo_rounds WHERE id = ?", (round_id,)
    ).fetchone()


def bump_taboo_clues(round_id: int) -> int:
    with _db() as c:
        c.execute(
            "UPDATE taboo_rounds SET clues_used = clues_used + 1 WHERE id = ?",
            (round_id,),
        )
    row = _db().execute(
        "SELECT clues_used FROM taboo_rounds WHERE id = ?", (round_id,)
    ).fetchone()
    return row["clues_used"]


def finish_taboo(round_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE taboo_rounds SET stage = 'done' WHERE id = ?", (round_id,))


# -------------------------------------------- world's most beautiful place

def get_beautiful(chat_id: int) -> dict | None:
    row = _db().execute(
        "SELECT state FROM beautiful WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return json.loads(row["state"]) if row else None


def save_beautiful(chat_id: int, state: dict) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO beautiful (chat_id, state) VALUES (?, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET state = excluded.state",
            (chat_id, json.dumps(state)),
        )


def clear_beautiful(chat_id: int) -> None:
    with _db() as c:
        c.execute("DELETE FROM beautiful WHERE chat_id = ?", (chat_id,))


# --------------------------------------------------------------------- wordle

def wordle_day(day: str):
    return _db().execute(
        "SELECT * FROM wordle_days WHERE day = ?", (day,)
    ).fetchone()


def save_wordle_day(day: str, number: int, word: str) -> None:
    with _db() as c:
        c.execute(
            "INSERT OR IGNORE INTO wordle_days (day, number, word) VALUES (?, ?, ?)",
            (day, number, word),
        )


def wordle_play(user_id: int, day: str):
    return _db().execute(
        "SELECT * FROM wordle_plays WHERE user_id = ? AND day = ?", (user_id, day)
    ).fetchone()


def save_wordle_play(user_id: int, day: str, first_name: str,
                     guesses: list[str], done: bool, won: bool) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO wordle_plays (user_id, day, first_name, guesses, done, won) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (user_id, day) DO UPDATE SET "
            "  guesses = excluded.guesses, done = excluded.done, won = excluded.won",
            (user_id, day, first_name, json.dumps(guesses), int(done), int(won)),
        )


def wordle_finishers(chat_id: int, day: str):
    """Chat members (from the member cache) who finished today's puzzle."""
    return _db().execute(
        "SELECT p.* FROM wordle_plays p "
        "JOIN known_users k ON k.user_id = p.user_id AND k.chat_id = ? "
        "WHERE p.day = ? AND p.done = 1 ORDER BY p.rowid",
        (chat_id, day),
    ).fetchall()


def wordle_duel(chat_id: int, day: str):
    return _db().execute(
        "SELECT * FROM wordle_duels WHERE chat_id = ? AND day = ?", (chat_id, day)
    ).fetchone()


def save_wordle_duel(chat_id: int, day: str, winner_id: int | None) -> None:
    with _db() as c:
        c.execute(
            "INSERT OR IGNORE INTO wordle_duels (chat_id, day, winner_id) "
            "VALUES (?, ?, ?)",
            (chat_id, day, winner_id),
        )


def wordle_user_days(user_id: int) -> list:
    """All finished plays for a user: [(day, won, n_guesses)] newest first."""
    rows = _db().execute(
        "SELECT day, won, guesses FROM wordle_plays "
        "WHERE user_id = ? AND done = 1 ORDER BY day DESC",
        (user_id,),
    ).fetchall()
    return [(r["day"], bool(r["won"]), len(json.loads(r["guesses"]))) for r in rows]


def wordle_duel_wins(chat_id: int, user_id: int) -> int:
    row = _db().execute(
        "SELECT COUNT(*) AS n FROM wordle_duels WHERE chat_id = ? AND winner_id = ?",
        (chat_id, user_id),
    ).fetchone()
    return row["n"]


def chats_for_user(user_id: int) -> list[int]:
    rows = _db().execute(
        "SELECT chat_id FROM known_users WHERE user_id = ?", (user_id,)
    ).fetchall()
    return [r["chat_id"] for r in rows]


def chat_members(chat_id: int):
    return _db().execute(
        "SELECT user_id, first_name FROM known_users WHERE chat_id = ?", (chat_id,)
    ).fetchall()


# -------------------------------------------------------------- daily question

def dailyq_get(chat_id: int):
    return _db().execute(
        "SELECT * FROM dailyq WHERE chat_id = ?", (chat_id,)
    ).fetchone()


def dailyq_all():
    return _db().execute("SELECT * FROM dailyq").fetchall()


def dailyq_set(chat_id: int, hour: int, minute: int) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO dailyq (chat_id, hour, minute) VALUES (?, ?, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET hour = excluded.hour, "
            "  minute = excluded.minute",
            (chat_id, hour, minute),
        )


def dailyq_bump(chat_id: int) -> int:
    """Advance the question index and return the index to use now."""
    with _db() as c:
        c.execute("UPDATE dailyq SET idx = idx + 1 WHERE chat_id = ?", (chat_id,))
    row = _db().execute(
        "SELECT idx FROM dailyq WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return row["idx"] - 1 if row else 0


def dailyq_off(chat_id: int) -> None:
    with _db() as c:
        c.execute("DELETE FROM dailyq WHERE chat_id = ?", (chat_id,))


# ------------------------------------------------------------------- paranoia

def create_paranoia(chat_id, target_id, target_name, question) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO paranoia_rounds (chat_id, target_id, target_name, question) "
            "VALUES (?, ?, ?, ?)",
            (chat_id, target_id, target_name, question),
        )
    return cur.lastrowid


def get_paranoia(round_id: int):
    return _db().execute(
        "SELECT * FROM paranoia_rounds WHERE id = ?", (round_id,)
    ).fetchone()


def finish_paranoia(round_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE paranoia_rounds SET stage = 'done' WHERE id = ?", (round_id,))
