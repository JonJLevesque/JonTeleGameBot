# AJBot 🎉🍪 (Audrey & Jon)

A Telegram group-chat bot with party games, a cookie economy, and inline-keyboard
board games (Tic-Tac-Toe, Reversi, Checkers). Built with
[python-telegram-bot](https://python-telegram-bot.org/) v21+ and SQLite — cookie
balances and in-progress games survive restarts.

Two features worth knowing up front:

- **AI-generated prompts (optional).** Set `ANTHROPIC_API_KEY` and every
  truth/dare/would-you-rather/paranoia/roleplay prompt is generated fresh by
  Claude, tailored to your chat (member names, spicy mode, group vs duo) — so
  content never repeats or runs out. Without a key, the bot uses its built-in
  static banks. Any AI failure silently falls back to the banks; the bot never
  blocks on the API.
- **Duo mode (automatic).** In a group with exactly two humans, the bot detects
  it and switches to prompts written for two people ("what did you think of
  {them} the first time you met?") instead of pointless "who in this chat…"
  questions. No configuration needed.

## Features

| Command | What it does |
|---|---|
| `/truthordare` | Random truth or dare prompt |
| `/wouldyourather` | Random "would you rather" dilemma |
| `/paranoia [@user]` | Whispers a secret question to a player (via a button only they can open); they answer aloud, then flip a coin — heads reveals the question, tails keeps it secret. Refusing costs a dare. |
| `/taboo` | The bot whispers you a secret phrase (e.g. "I hate you"); make the chat guess it **without using any of its key words** (stopwords like "but"/"no" are allowed in clues), in at most 3 clue messages. The bot referees automatically: it counts your clues, catches forbidden words, detects correct guesses, and pays a 🍪 to both guesser and describer. Needs privacy mode disabled (see setup). |
| `/roleplay` | Generates a random scenario and assigns random roles to up to 4 chat members to act out |
| `/spicymode on\|off` | Chat admins only: unlock Spicy🌶️ (flirty, adults-only) prompt pools for /truthordare, /wouldyourather and /roleplay in this chat. All spicy prompts are about members of *this chat* — many inject a random member's name — never outside crushes/partners. |
| `/cookie @user` | Award a cookie (also works as a reply to someone's message) |
| `/cookies [@user]` | Check a cookie balance (yours by default) |
| `/cookieboard` | Top 10 cookie holders in this chat |
| `/tictactoe [@user]` | Challenge to Tic-Tac-Toe (omit the user for an open challenge) |
| `/reversi [@user]` | Challenge to Reversi/Othello |
| `/checkers [@user]` | Challenge to Checkers (English draughts: mandatory captures, multi-jumps, kings) |
| `/chess [@user]` | Challenge to Chess — full rules via python-chess (castling, en passant, promotion picker, checkmate/stalemate/dead-position detection). Tap a piece, then a highlighted square. |
| `/beautiful [status\|reset]` | **World's Most Beautiful Place** — ~2000 famous places (from Wikidata/Wikimedia Commons, built by `scripts/fetch_places.py`) enter a single-elimination photo knockout. Each `/beautiful` posts one head-to-head: two photos + 🅰️/🅱️ buttons. The matchup waits until **two different people** vote: 2–0 advances the winner; 1–1 lets both survive into the next round (in the final: one rematch, then a coin flip). The bracket is saved per chat and can idle for weeks — summon the next matchup whenever. Rebuilding `places.json` mid-tournament scrambles photo ids, so `/beautiful reset` after a rebuild. |
| `/wordle` | **Competitive daily Wordle** — the bot fetches the real NYT word of the day (public endpoint, local fallback list), each player plays privately in a DM with the bot, and finished boards (squares only) auto-post to shared group chats. When a second chat member finishes, the bot announces the head-to-head: fewer guesses wins +1 🍪. `/wordle` in the group shows standings, duel wins, streaks and averages. |
| `/dailyq on [HH:MM]\|now\|off` | **Daily question ritual** — one question per day (default 20:00), walking an escalating "36 questions"-style arc: warm-up → personal → about-the-two-of-you → deep (plus a steamy tier when `/spicymode` is on). Past the scripted arc, questions are AI-generated at the deepest stage when `ANTHROPIC_API_KEY` is set. Schedule and arc position survive restarts. |
| `/tournament Title: a, b, c` | Knockout bracket for **any list** (movies, date ideas…) — same two-vote engine as `/beautiful` (shared `handlers/bracket.py`). `reset` wipes it. |
| `/whereami` | Geo-guessing round from the places pool: mystery photo, four country buttons, reveal after two guesses, correct = 🍪. |
| `/settle <argument>` | The bot's supreme court rules on any dispute — decisively, with a roast (AI-judged; coin-flip verdict without a key). Reply to a message with `/settle` to enter it into evidence. |
| `/shop`, `/redeem <id>` | IOU shop: the chat defines real-world rewards (`/shop add 50 loser cooks dinner`), bought with cookies. All cookie movement is logged. |
| `/recap on\|now\|off` | Sunday 19:00 weekly scoreboard: Wordle duels/streaks, cookie movement, bracket progress, games played. |
| `/help` | List all commands |

**Wagers:** any board-game challenge takes an optional stake — `/chess @rival 10`. Stakes are escrowed when the challenge is accepted; winner takes the pot, draws refund. Boards have a two-tap 🏳️ Resign and a 🔄 Rematch button.

**Ops:** `scripts/install_launchd.sh` installs the bot as a macOS launchd agent (auto-start, auto-restart, logs in `~/Library/Logs/ajbot/`). Nightly SQLite backups land in `backups/` (kept out of git). Crashes are DM'd to `BOT_ADMIN_ID`. `scripts/announce_update.sh <chat_id> "line"…` posts a changelog to the chat as the bot.

Board games use a challenge → accept/decline flow (the challenger can cancel a
hanging challenge via the Decline button), then play entirely through inline
keyboards. Any number of games can run at the same time, across any number of
chats.

## Setup

### 1. Get a bot token

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, pick a display name and a unique username ending in `bot`.
3. BotFather replies with a token like `123456789:AAF-abc...` — copy it.
4. Recommended: send BotFather `/setprivacy`, select your bot, choose
   **Disable**. This lets the bot see regular group messages, which is
   **required for `/taboo`** (the bot referees clues and guesses) and lets it
   learn members' usernames (for `/cookie @username`-style targeting,
   leaderboard names, and `/roleplay` casting). With privacy **enabled**
   everything else still works, but the bot only learns members when they use
   a command or are replied to — the fallback is always "reply to their
   message".

### 2. Install and run

Requires Python 3.10+ — check with `python3 --version`. On macOS the system
`python3` is often 3.9; use a Homebrew build instead (e.g. `brew install
python@3.13`, then substitute `python3.13` below).

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export TELEGRAM_BOT_TOKEN='123456789:AAF-your-token-here'
export BOT_DB_PATH='ajbot.db'     # optional, this is the default

# Optional — AI-generated prompts via the Claude API (console.anthropic.com):
export ANTHROPIC_API_KEY='sk-ant-...'
export AI_MODEL='claude-opus-5'      # optional, this is the default

python bot.py
```

### 3. Add it to a group

Invite the bot to your group like any member. If you want slash-command
autocomplete, the bot registers its command list with Telegram automatically on
startup.

## Project structure

```
bot.py                  Entry point: builds the Application, registers handlers
config.py               Environment-variable config (token, DB path, AI key)
ai.py                   Optional Claude-powered prompt generation (static fallback)
db.py                   All SQLite persistence (cookies, games, paranoia, user cache)
prompts.py              Static prompt banks: per category, any-size + group-only
                        + duo variants, assembled by prompts.pool()
games/                  Pure game logic — no Telegram imports
  base.py               TwoPlayerBoardGame abstraction (state, moves, render, outcome)
  tictactoe.py          3x3 with win/draw detection
  reversi.py            8x8 with flip logic, auto-pass, disc-count scoring
  checkers.py           English draughts: mandatory captures, multi-jumps, kings
  __init__.py           GAME_REGISTRY — add a game class here and it's live
handlers/               Telegram-facing layer
  common.py             Shared helpers (group check, @user/reply target resolution)
  help.py               /start, /help, command list for autocomplete
  party.py              /truthordare, /wouldyourather, /paranoia
  taboo.py              /taboo + the message listener that referees rounds
  roleplay.py           /roleplay, /spicymode (per-chat Spicy🌶️ toggle)
  cookies.py            /cookie, /cookies, /cookieboard
  boardgames.py         Challenge flow + generic move routing for all board games
```

### How the layers separate

- **Game logic** (`games/`) knows nothing about Telegram. A game is a dict of
  JSON-serializable state plus four class methods: `new_state`, `apply(state,
  player, payload)`, `keyboard(state)` (returns `(label, payload)` cells), and
  `outcome(state)`. Adding a game = one new subclass + one registry entry;
  the challenge flow, turn enforcement, persistence, and rendering are shared.
  (Chess was deliberately left out — doing it robustly needs a dedicated
  move-validation module, per the design notes in `games/base.py`.)
- **Persistence** (`db.py`) owns every SQL statement. Game state is stored as a
  JSON blob keyed by game id; the game id rides inside each button's callback
  data, so a restarted bot picks up mid-game taps seamlessly.
- **Handlers** (`handlers/`) translate Telegram updates into game/db calls and
  render results back. A per-game `asyncio.Lock` serializes simultaneous taps
  on the same board; different games never contend.

### Notes & limitations

- The Bot API cannot resolve `@username` → user id, so the bot caches members
  it has seen (`known_users` table). Until someone has spoken, target them by
  replying to their message.
- Paranoia's "whisper" uses a callback alert (visible only to the tapper), so
  players do **not** need to have DMed the bot first.
- Checkers has no draw detection (threefold repetition etc.) — players can
  agree to abandon a dead position.
- `/taboo` allows one active round per chat at a time; the describer can end a
  stuck round with the 🏳️ Give up button.
- Spicy mode is per-chat, off by default, admin-gated, and keeps to flirty
  party-game prompts. Admins are responsible for making sure everyone in the
  chat is an adult before turning it on.
