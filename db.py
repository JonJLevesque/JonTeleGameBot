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

        CREATE TABLE IF NOT EXISTS tournaments (
            chat_id INTEGER PRIMARY KEY,
            state   TEXT NOT NULL              -- JSON blob owned by handlers/tournament.py
        );

        CREATE TABLE IF NOT EXISTS cookie_log (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            delta   INTEGER NOT NULL,
            reason  TEXT,
            ts      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS shop_items (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            price   INTEGER NOT NULL,
            reward  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recap_chats (
            chat_id        INTEGER PRIMARY KEY,
            last_beautiful INTEGER NOT NULL DEFAULT 0
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

        CREATE TABLE IF NOT EXISTS whispers (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id      INTEGER NOT NULL,
            sender_name    TEXT NOT NULL,
            recipient_id   INTEGER NOT NULL,
            recipient_name TEXT NOT NULL,
            message        TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'pending',  -- pending | delivered
            created_at     TEXT DEFAULT (datetime('now')),
            delivered_at   TEXT,
            deliver_at     TEXT,                    -- UTC; NULL = deliver now
            kind           TEXT NOT NULL DEFAULT 'whisper',  -- whisper | capsule
            teased         INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_whispers_pending
            ON whispers (recipient_id) WHERE status = 'pending';

        CREATE TABLE IF NOT EXISTS quotes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id       INTEGER NOT NULL,
            message_id    INTEGER,
            author_id     INTEGER,
            author_name   TEXT NOT NULL,
            text          TEXT NOT NULL,
            saved_by_id   INTEGER NOT NULL,
            saved_by_name TEXT NOT NULL,
            ts            TEXT DEFAULT (datetime('now')),
            UNIQUE (chat_id, message_id)
        );

        CREATE TABLE IF NOT EXISTS memories (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id       INTEGER NOT NULL,
            about_user_id INTEGER,               -- NULL = about the chat
            text          TEXT NOT NULL,
            source        TEXT NOT NULL,         -- told | observed
            created_at    TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_memories_chat ON memories (chat_id);

        CREATE TABLE IF NOT EXISTS tod_bags (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            bag     TEXT NOT NULL DEFAULT '[]',  -- JSON list of pending draws
            PRIMARY KEY (chat_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS daily_claims (
            chat_id  INTEGER NOT NULL,
            user_id  INTEGER NOT NULL,
            last_day TEXT NOT NULL,               -- ISO date of last claim
            streak   INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (chat_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS drops (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id    INTEGER NOT NULL,
            kind       TEXT NOT NULL,             -- crate | trap
            amount     INTEGER NOT NULL,
            claimed_by INTEGER,                   -- NULL until claimed
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS casino_hands (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id    INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            stake      INTEGER NOT NULL,
            state      TEXT NOT NULL,             -- JSON blob owned by handlers/casino.py
            status     TEXT NOT NULL DEFAULT 'active',  -- active | finished
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_levels (
            chat_id         INTEGER PRIMARY KEY,
            announced_level INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pets (
            chat_id INTEGER PRIMARY KEY,
            state   TEXT NOT NULL                 -- JSON blob owned by handlers/pet.py
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
    _ensure_column("games", "stake", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column("whispers", "deliver_at", "TEXT")
    _ensure_column("whispers", "kind", "TEXT NOT NULL DEFAULT 'whisper'")
    _ensure_column("whispers", "teased", "INTEGER NOT NULL DEFAULT 0")
    _conn.commit()


def _ensure_column(table: str, col: str, decl: str) -> None:
    """Tiny migration helper: add a column if an older DB lacks it."""
    cols = {r["name"] for r in _conn.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        _conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


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

def add_cookies(chat_id: int, user_id: int, delta: int, reason: str = "") -> int:
    """Adjust a balance (logged for weekly recaps) and return the new total."""
    with _db() as c:
        c.execute(
            "INSERT INTO cookies (chat_id, user_id, count) VALUES (?, ?, ?) "
            "ON CONFLICT (chat_id, user_id) DO UPDATE SET count = count + ?",
            (chat_id, user_id, delta, delta),
        )
        c.execute(
            "INSERT INTO cookie_log (chat_id, user_id, delta, reason) "
            "VALUES (?, ?, ?, ?)",
            (chat_id, user_id, delta, reason),
        )
    return get_cookies(chat_id, user_id)


def cookie_deltas_since(chat_id: int, since_ts: str):
    """[(user_id, net_delta)] since an ISO timestamp, biggest movers first."""
    rows = _db().execute(
        "SELECT user_id, SUM(delta) AS d FROM cookie_log "
        "WHERE chat_id = ? AND ts >= ? GROUP BY user_id ORDER BY d DESC",
        (chat_id, since_ts),
    ).fetchall()
    return [(r["user_id"], r["d"]) for r in rows]


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


# ----------------------------------------------------------------- IOU shop

def shop_add(chat_id: int, price: int, reward: str) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO shop_items (chat_id, price, reward) VALUES (?, ?, ?)",
            (chat_id, price, reward),
        )
    return cur.lastrowid


def shop_list(chat_id: int):
    return _db().execute(
        "SELECT * FROM shop_items WHERE chat_id = ? ORDER BY price", (chat_id,)
    ).fetchall()


def shop_get(chat_id: int, item_id: int):
    return _db().execute(
        "SELECT * FROM shop_items WHERE chat_id = ? AND id = ?",
        (chat_id, item_id),
    ).fetchone()


def shop_remove(chat_id: int, item_id: int) -> bool:
    with _db() as c:
        cur = c.execute(
            "DELETE FROM shop_items WHERE chat_id = ? AND id = ?",
            (chat_id, item_id),
        )
    return cur.rowcount > 0


# ---------------------------------------------------------------- board games

def create_game(chat_id, game_type, p0_id, p0_name, p1_id, p1_name,
                stake: int = 0) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO games (chat_id, game_type, p0_id, p0_name, p1_id, "
            "p1_name, stake) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chat_id, game_type, p0_id, p0_name, p1_id, p1_name, stake),
        )
    return cur.lastrowid


def escrow_and_activate(game, p1_id: int, p1_name: str, state: dict) -> bool:
    """Accept a challenge atomically: verify + deduct both stakes and flip
    the game to active in ONE transaction, so a crash can never strand an
    escrowed stake on a still-pending game. False if a balance fell short."""
    stake = game["stake"]
    with _db() as c:
        if stake:
            for uid in (game["p0_id"], p1_id):
                row = c.execute(
                    "SELECT count FROM cookies WHERE chat_id = ? AND user_id = ?",
                    (game["chat_id"], uid),
                ).fetchone()
                if (row["count"] if row else 0) < stake:
                    return False
            for uid in (game["p0_id"], p1_id):
                c.execute(
                    "UPDATE cookies SET count = count - ? "
                    "WHERE chat_id = ? AND user_id = ?",
                    (stake, game["chat_id"], uid),
                )
                c.execute(
                    "INSERT INTO cookie_log (chat_id, user_id, delta, reason) "
                    "VALUES (?, ?, ?, 'wager escrow')",
                    (game["chat_id"], uid, -stake),
                )
        c.execute(
            "UPDATE games SET status = 'active', state = ?, p1_id = ?, "
            "p1_name = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(state), p1_id, p1_name, game["id"]),
        )
    return True


def finished_games_since(chat_id: int, since_ts: str) -> int:
    row = _db().execute(
        "SELECT COUNT(*) AS n FROM games WHERE chat_id = ? "
        "AND status = 'finished' AND updated_at >= ? AND state IS NOT NULL",
        (chat_id, since_ts),
    ).fetchone()
    return row["n"]


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
        # re-baseline the weekly-recap snapshot for the next bracket
        c.execute(
            "UPDATE recap_chats SET last_beautiful = 0 WHERE chat_id = ?",
            (chat_id,),
        )


# ----------------------------------------------------- custom tournaments

def get_tournament(chat_id: int) -> dict | None:
    row = _db().execute(
        "SELECT state FROM tournaments WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return json.loads(row["state"]) if row else None


def save_tournament(chat_id: int, state: dict) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO tournaments (chat_id, state) VALUES (?, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET state = excluded.state",
            (chat_id, json.dumps(state)),
        )


def clear_tournament(chat_id: int) -> None:
    with _db() as c:
        c.execute("DELETE FROM tournaments WHERE chat_id = ?", (chat_id,))


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


def wordle_duel_wins_since(chat_id: int, user_id: int, since_day: str) -> int:
    row = _db().execute(
        "SELECT COUNT(*) AS n FROM wordle_duels "
        "WHERE chat_id = ? AND winner_id = ? AND day >= ?",
        (chat_id, user_id, since_day),
    ).fetchone()
    return row["n"]


def chats_with_min_members(n: int = 2) -> list[int]:
    rows = _db().execute(
        "SELECT chat_id FROM known_users GROUP BY chat_id "
        "HAVING COUNT(*) >= ?", (n,),
    ).fetchall()
    return [r["chat_id"] for r in rows]


# -------------------------------------------------------------- weekly recap

def recap_on(chat_id: int) -> None:
    with _db() as c:
        c.execute(
            "INSERT OR IGNORE INTO recap_chats (chat_id) VALUES (?)", (chat_id,)
        )


def recap_off(chat_id: int) -> None:
    with _db() as c:
        c.execute("DELETE FROM recap_chats WHERE chat_id = ?", (chat_id,))


def recap_all() -> list[int]:
    return [r["chat_id"] for r in _db().execute("SELECT chat_id FROM recap_chats")]


def recap_snapshot(chat_id: int) -> int | None:
    row = _db().execute(
        "SELECT last_beautiful FROM recap_chats WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return row["last_beautiful"] if row else None


def recap_update_snapshot(chat_id: int, match_no: int) -> None:
    with _db() as c:
        c.execute(
            "UPDATE recap_chats SET last_beautiful = ? WHERE chat_id = ?",
            (match_no, chat_id),
        )


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


# ------------------------------------------------------------------- whispers

def create_whisper(sender_id: int, sender_name: str, recipient_id: int,
                   recipient_name: str, message: str,
                   deliver_at: str | None = None,
                   kind: str = "whisper") -> int:
    """deliver_at is a UTC 'YYYY-MM-DD HH:MM:SS' string; NULL delivers now."""
    with _db() as c:
        cur = c.execute(
            "INSERT INTO whispers (sender_id, sender_name, recipient_id, "
            "recipient_name, message, deliver_at, kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sender_id, sender_name, recipient_id, recipient_name, message,
             deliver_at, kind),
        )
    return cur.lastrowid


def pending_whispers(recipient_id: int):
    """Undelivered whispers for a user that are due (a scheduled whisper or
    capsule stays sealed until its deliver_at passes), oldest first."""
    return _db().execute(
        "SELECT * FROM whispers WHERE recipient_id = ? AND status = 'pending' "
        "AND (deliver_at IS NULL OR deliver_at <= datetime('now')) "
        "ORDER BY id",
        (recipient_id,),
    ).fetchall()


def due_whispers():
    """Scheduled whispers/capsules whose delivery time has arrived, oldest
    first. Used by the courier job; immediate whispers never appear here."""
    return _db().execute(
        "SELECT * FROM whispers WHERE status = 'pending' "
        "AND deliver_at IS NOT NULL AND deliver_at <= datetime('now') "
        "ORDER BY id"
    ).fetchall()


def mark_whisper_teased(whisper_id: int) -> None:
    """Remember that the 'you've got mail' group tease was posted, so the
    minutely courier job never announces the same whisper twice."""
    with _db() as c:
        c.execute("UPDATE whispers SET teased = 1 WHERE id = ?", (whisper_id,))


def mark_whisper_delivered(whisper_id: int) -> None:
    with _db() as c:
        c.execute(
            "UPDATE whispers SET status = 'delivered', "
            "delivered_at = datetime('now') WHERE id = ?",
            (whisper_id,),
        )


def resolve_recipient(sender_id: int, token: str) -> list[tuple[int, str]]:
    """Candidates for a whisper recipient: users who share a chat with the
    sender, matched by @username or (case-insensitive) first name. One row
    per user_id, so someone known in several shared chats appears once."""
    shared = ("SELECT chat_id FROM known_users WHERE user_id = ?")
    if token.startswith("@"):
        where, value = "username = ?", token.lstrip("@").lower()
    else:
        where, value = "LOWER(first_name) = LOWER(?)", token
    rows = _db().execute(
        f"SELECT user_id, MAX(first_name) AS first_name FROM known_users "
        f"WHERE chat_id IN ({shared}) AND {where} AND user_id != ? "
        f"GROUP BY user_id",
        (sender_id, value, sender_id),
    ).fetchall()
    return [(r["user_id"], r["first_name"]) for r in rows]


def shared_chats(user_a: int, user_b: int) -> list[int]:
    """Group chats where both users are known."""
    rows = _db().execute(
        "SELECT chat_id FROM known_users WHERE user_id = ? "
        "AND chat_id IN (SELECT chat_id FROM known_users WHERE user_id = ?)",
        (user_a, user_b),
    ).fetchall()
    return [r["chat_id"] for r in rows]


# ----------------------------------------------------------------- memories

MEMORY_CAP = 200  # per chat; oldest evicted beyond this


def add_memory(chat_id: int, text: str, source: str,
               about_user_id: int | None = None) -> int | None:
    """Store one short fact about the chat. Near-duplicates (case-insensitive
    exact text) are skipped; beyond MEMORY_CAP the oldest facts are evicted."""
    text = " ".join(text.split())[:200]
    if not text:
        return None
    with _db() as c:
        dup = c.execute(
            "SELECT id FROM memories WHERE chat_id = ? AND LOWER(text) = LOWER(?)",
            (chat_id, text),
        ).fetchone()
        if dup:
            return None
        cur = c.execute(
            "INSERT INTO memories (chat_id, about_user_id, text, source) "
            "VALUES (?, ?, ?, ?)",
            (chat_id, about_user_id, text, source),
        )
        c.execute(
            "DELETE FROM memories WHERE chat_id = ? AND id NOT IN "
            "(SELECT id FROM memories WHERE chat_id = ? ORDER BY id DESC LIMIT ?)",
            (chat_id, chat_id, MEMORY_CAP),
        )
    return cur.lastrowid


def memories_all(chat_id: int):
    return _db().execute(
        "SELECT * FROM memories WHERE chat_id = ? ORDER BY id", (chat_id,)
    ).fetchall()


def memories_since(chat_id: int, since_ts: str):
    return _db().execute(
        "SELECT * FROM memories WHERE chat_id = ? AND created_at >= ? "
        "ORDER BY id", (chat_id, since_ts),
    ).fetchall()


def delete_memory(chat_id: int, memory_id: int) -> bool:
    with _db() as c:
        cur = c.execute(
            "DELETE FROM memories WHERE chat_id = ? AND id = ?",
            (chat_id, memory_id),
        )
    return cur.rowcount > 0


def find_memories(chat_id: int, hint: str):
    return _db().execute(
        "SELECT * FROM memories WHERE chat_id = ? AND text LIKE ? ORDER BY id",
        (chat_id, f"%{hint}%"),
    ).fetchall()


def relevant_memories(chat_id: int, text: str = "", limit: int = 30) -> list[str]:
    """Memory texts for an AI context block: keyword hits on the message
    first (words of 4+ letters), then the most recent facts, deduped."""
    rows = memories_all(chat_id)
    if not rows:
        return []
    words = {w for w in text.lower().split() if len(w) >= 4}
    hits = [r["text"] for r in rows
            if words and any(w in r["text"].lower() for w in words)]
    recent = [r["text"] for r in reversed(rows)]
    out: list[str] = []
    for t in hits + recent:
        if t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------- truth-or-dare bags

def get_tod_bag(chat_id: int, user_id: int) -> list[str]:
    row = _db().execute(
        "SELECT bag FROM tod_bags WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    ).fetchone()
    return json.loads(row["bag"]) if row else []


def set_tod_bag(chat_id: int, user_id: int, bag: list[str]) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO tod_bags (chat_id, user_id, bag) VALUES (?, ?, ?) "
            "ON CONFLICT (chat_id, user_id) DO UPDATE SET bag = excluded.bag",
            (chat_id, user_id, json.dumps(bag)),
        )


# ----------------------------------------------------- daily claims & drops

def daily_claim(chat_id: int, user_id: int, today: str,
                yesterday: str) -> tuple[bool, int]:
    """Claim today's daily. Returns (claimed, streak): claimed is False when
    already claimed today (streak is the current one); a claim the day after
    the last one extends the streak, any longer gap resets it to 1."""
    with _db() as c:
        row = c.execute(
            "SELECT last_day, streak FROM daily_claims "
            "WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()
        if row and row["last_day"] == today:
            return False, row["streak"]
        streak = row["streak"] + 1 if row and row["last_day"] == yesterday else 1
        c.execute(
            "INSERT INTO daily_claims (chat_id, user_id, last_day, streak) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (chat_id, user_id) DO UPDATE SET "
            "  last_day = excluded.last_day, streak = excluded.streak",
            (chat_id, user_id, today, streak),
        )
    return True, streak


def create_drop(chat_id: int, kind: str, amount: int) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO drops (chat_id, kind, amount) VALUES (?, ?, ?)",
            (chat_id, kind, amount),
        )
    return cur.lastrowid


def claim_drop(drop_id: int, user_id: int):
    """First-tap-wins: atomically claim a drop. Returns the drop row on
    success, or None if someone else got there first (or it doesn't exist)."""
    with _db() as c:
        cur = c.execute(
            "UPDATE drops SET claimed_by = ? "
            "WHERE id = ? AND claimed_by IS NULL",
            (user_id, drop_id),
        )
        if cur.rowcount == 0:
            return None
    return _db().execute(
        "SELECT * FROM drops WHERE id = ?", (drop_id,)
    ).fetchone()


# --------------------------------------------------------------------- casino

def create_casino_hand(chat_id: int, user_id: int, stake: int,
                       state: dict) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO casino_hands (chat_id, user_id, stake, state) "
            "VALUES (?, ?, ?, ?)",
            (chat_id, user_id, stake, json.dumps(state)),
        )
    return cur.lastrowid


def get_casino_hand(hand_id: int):
    return _db().execute(
        "SELECT * FROM casino_hands WHERE id = ?", (hand_id,)
    ).fetchone()


def active_casino_hand(chat_id: int, user_id: int):
    return _db().execute(
        "SELECT * FROM casino_hands WHERE chat_id = ? AND user_id = ? "
        "AND status = 'active' ORDER BY id DESC LIMIT 1",
        (chat_id, user_id),
    ).fetchone()


def update_casino_hand(hand_id: int, *, state: dict | None = None,
                       status: str | None = None) -> None:
    sets, args = [], []
    if state is not None:
        sets.append("state = ?"); args.append(json.dumps(state))
    if status is not None:
        sets.append("status = ?"); args.append(status)
    args.append(hand_id)
    with _db() as c:
        c.execute(f"UPDATE casino_hands SET {', '.join(sets)} WHERE id = ?", args)


# ---------------------------------------------------------------- XP & levels

def xp_stats(chat_id: int) -> dict:
    """Raw lifetime activity counts for the chat's shared level. The level
    handler owns the weights; this just counts. Whisper/wordle counts join
    through known_users, so in the (unlikely) multi-group case a member's
    DM-based activity counts toward every chat they're in."""
    q = _db().execute
    n = lambda sql, *a: q(sql, a).fetchone()[0]  # noqa: E731
    dq = q("SELECT idx FROM dailyq WHERE chat_id = ?", (chat_id,)).fetchone()
    return {
        "games": n(
            "SELECT COUNT(*) FROM games WHERE chat_id = ? "
            "AND status = 'finished' AND state IS NOT NULL", chat_id),
        "wordle": n(
            "SELECT COUNT(*) FROM wordle_plays p JOIN known_users k "
            "ON k.user_id = p.user_id AND k.chat_id = ? WHERE p.done = 1",
            chat_id),
        "quotes": n("SELECT COUNT(*) FROM quotes WHERE chat_id = ?", chat_id),
        "whispers": n(
            "SELECT COUNT(*) FROM whispers w WHERE w.status = 'delivered' "
            "AND EXISTS (SELECT 1 FROM known_users k WHERE k.chat_id = ? "
            "AND k.user_id = w.sender_id)", chat_id),
        "taboo": n(
            "SELECT COUNT(*) FROM taboo_rounds WHERE chat_id = ? "
            "AND stage = 'done'", chat_id),
        "paranoia": n(
            "SELECT COUNT(*) FROM paranoia_rounds WHERE chat_id = ? "
            "AND stage = 'done'", chat_id),
        "cookie_moves": n(
            "SELECT COUNT(*) FROM cookie_log WHERE chat_id = ?", chat_id),
        "dailyq": dq["idx"] if dq else 0,
    }


def get_announced_level(chat_id: int) -> int:
    row = _db().execute(
        "SELECT announced_level FROM chat_levels WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return row["announced_level"] if row else 0


def set_announced_level(chat_id: int, level: int) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO chat_levels (chat_id, announced_level) VALUES (?, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET "
            "  announced_level = excluded.announced_level",
            (chat_id, level),
        )


# ------------------------------------------------------------------ shared pet

def get_pet(chat_id: int) -> dict | None:
    row = _db().execute(
        "SELECT state FROM pets WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return json.loads(row["state"]) if row else None


def save_pet(chat_id: int, state: dict) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO pets (chat_id, state) VALUES (?, ?) "
            "ON CONFLICT (chat_id) DO UPDATE SET state = excluded.state",
            (chat_id, json.dumps(state)),
        )


def clear_pet(chat_id: int) -> None:
    with _db() as c:
        c.execute("DELETE FROM pets WHERE chat_id = ?", (chat_id,))


def all_pets() -> list[tuple[int, dict]]:
    return [(r["chat_id"], json.loads(r["state"]))
            for r in _db().execute("SELECT * FROM pets")]


# --------------------------------------------------------------- quote wall

def save_quote(chat_id: int, message_id: int | None, author_id: int | None,
               author_name: str, text: str,
               saved_by_id: int, saved_by_name: str) -> int | None:
    """Preserve a message for posterity. None if it was already saved."""
    try:
        with _db() as c:
            cur = c.execute(
                "INSERT INTO quotes (chat_id, message_id, author_id, "
                "author_name, text, saved_by_id, saved_by_name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chat_id, message_id, author_id, author_name, text,
                 saved_by_id, saved_by_name),
            )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def random_quote(chat_id: int, like: str | None = None,
                 since_ts: str | None = None):
    """A random saved quote, optionally filtered by substring or recency."""
    where, args = ["chat_id = ?"], [chat_id]
    if like:
        where.append("text LIKE ?")
        args.append(f"%{like}%")
    if since_ts:
        where.append("ts >= ?")
        args.append(since_ts)
    return _db().execute(
        f"SELECT * FROM quotes WHERE {' AND '.join(where)} "
        f"ORDER BY RANDOM() LIMIT 1",
        args,
    ).fetchone()


def quote_count(chat_id: int) -> int:
    row = _db().execute(
        "SELECT COUNT(*) AS n FROM quotes WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return row["n"]


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
