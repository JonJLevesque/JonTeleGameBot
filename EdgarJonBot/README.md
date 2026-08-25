# EdgarJonBot

The third dev in a two-person chat. Listens to everything, files away ideas
and facts, answers when addressed, reminds, summarizes, settles arguments,
and posts a Sunday recap.

## Setup

1. `@BotFather` → `/newbot` → copy the token.
2. `@BotFather` → `/setprivacy` → pick the bot → **Disable**. Without this the
   bot only sees commands and @mentions, and the passive listening does nothing.
3. Add the bot to the group. Say something. `/help`.

```sh
export TELEGRAM_BOT_TOKEN='…'
export ANTHROPIC_API_KEY='…'        # optional but it's most of the point
export BOT_ADMIN_ID=…               # optional: crash alerts DM'd here
../.venv/bin/python bot.py
```

Env knobs: `BOT_NAME` (default "Edgar Jr."), `AI_MODEL` (default
`claude-opus-5`), `BOT_CHIME_IN_RATE` (0.04), `BOT_EXTRACT_EVERY` (12),
`BOT_EXTRACT_IDLE_MINUTES` (15).

## Running under launchd

Copy `launchd/com.jonl.edgarjonbot.plist` to `~/Library/LaunchAgents/`,
fill in the token/key, then
`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jonl.edgarjonbot.plist`.
Restart after changes: `launchctl kickstart -k gui/$(id -u)/com.jonl.edgarjonbot`.

## Layout

- `bot.py` — wiring, jobs, error alerts
- `ai.py` — persona + every Claude call (structured outputs for extraction/reminders)
- `db.py` — SQLite: messages, ideas, shipped, facts, reminders, duck sessions
- `handlers/listener.py` — logs messages, replies when addressed, distills ideas/facts
- `handlers/{ideas,shipping,reminders,brain,tools,help}.py` — commands

## Tests

`../.venv/bin/python -m pytest tests -q`
