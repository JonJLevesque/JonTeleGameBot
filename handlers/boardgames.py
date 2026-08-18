"""Board games: challenge flow + inline-keyboard play for every game in
games.GAME_REGISTRY.

Callback data format: "bg:<game_id>:<payload>" where payload is
"a" (accept), "d" (decline/cancel), "x" (inert button), or a game-specific
move string handed to the game class untouched. Because the game id rides in
the callback data and all state lives in SQLite, in-progress games keep
working across bot restarts, and any number of games can run at once —
a per-game asyncio lock serializes concurrent taps on the same board.
"""
import asyncio
import json
from collections import defaultdict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import db
from games import GAME_REGISTRY, NOOP
from .common import require_group, target_from_message

_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def _markup(cls, state, game_id: int, frozen: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for row in cls.keyboard(state):
        rows.append([
            InlineKeyboardButton(
                label,
                callback_data=f"bg:{game_id}:{NOOP if frozen else payload}",
            )
            for label, payload in row
        ])
    return InlineKeyboardMarkup(rows)


def _header(cls, game) -> str:
    return (
        f"🎮 <b>{cls.name}</b>\n"
        f"{cls.symbols[0]} {game['p0_name']} vs {cls.symbols[1]} {game['p1_name']}"
    )


async def _edit(query, text: str, markup: InlineKeyboardMarkup | None):
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


def _make_start_handler(code: str):
    async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await require_group(update):
            return
        cls = GAME_REGISTRY[code]
        challenger = update.effective_user
        opp_id, opp_name = target_from_message(update, context)
        if opp_id is None and opp_name is not None:
            await update.effective_message.reply_text(opp_name)  # resolution error
            return
        if opp_id == challenger.id:
            await update.effective_message.reply_text(
                "You can't challenge yourself — pick a worthy opponent!"
            )
            return

        game_id = db.create_game(
            update.effective_chat.id, code, challenger.id, challenger.first_name,
            opp_id, opp_name,
        )
        who = f"<b>{opp_name}</b>" if opp_id else "anyone brave enough"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Accept", callback_data=f"bg:{game_id}:a"),
            InlineKeyboardButton("❌ Decline", callback_data=f"bg:{game_id}:d"),
        ]])
        msg = await update.effective_message.reply_html(
            f"🎮 <b>{cls.name}</b>\n"
            f"<b>{challenger.first_name}</b> challenges {who}!\n"
            f"({challenger.first_name} can tap Decline to cancel.)",
            reply_markup=keyboard,
        )
        db.set_game_message(game_id, msg.message_id)

    return start_game


async def _handle_pending(query, game, cls, payload):
    user = query.from_user
    open_challenge = game["p1_id"] is None

    if payload == "a":
        if user.id == game["p0_id"]:
            await query.answer("You can't accept your own challenge!")
            return
        if not open_challenge and user.id != game["p1_id"]:
            await query.answer(f"This challenge is for {game['p1_name']}.")
            return
        db.update_game(
            game["id"], status="active", state=cls.new_state(),
            p1_id=user.id, p1_name=user.first_name,
        )
        game = db.get_game(game["id"])
        state = json.loads(game["state"])
        await query.answer("Game on!")
        await _edit(
            query,
            f"{_header(cls, game)}\n\n{cls.status_line(state, (game['p0_name'], game['p1_name']))}",
            _markup(cls, state, game["id"]),
        )
    elif payload == "d":
        if user.id == game["p0_id"]:
            text = f"🎮 {cls.name}: challenge cancelled by {game['p0_name']}."
        elif open_challenge or user.id == game["p1_id"]:
            text = f"🎮 {cls.name}: {user.first_name} declined the challenge."
        else:
            await query.answer(f"This challenge is for {game['p1_name']}.")
            return
        db.update_game(game["id"], status="finished")
        await query.answer()
        await _edit(query, text, None)
    else:
        await query.answer()


async def _handle_move(query, game, cls, payload):
    user = query.from_user
    players = (game["p0_id"], game["p1_id"])
    if user.id not in players:
        await query.answer("You're not in this game — start your own!")
        return
    player = players.index(user.id)
    state = json.loads(game["state"])
    if state["turn"] != player:
        await query.answer("Not your turn!")
        return

    error = cls.apply(state, player, payload)
    if error:
        await query.answer(error)
        return

    names = (game["p0_name"], game["p1_name"])
    result = cls.outcome(state)
    if result is None:
        db.update_game(game["id"], state=state)
        await query.answer()
        await _edit(
            query,
            f"{_header(cls, game)}\n\n{cls.status_line(state, names)}",
            _markup(cls, state, game["id"]),
        )
        return

    # Game over — freeze the board so leftover highlights aren't clickable.
    state["sel"] = None
    db.update_game(game["id"], state=state, status="finished")
    winner = result["winner"]
    if winner is None:
        verdict = "🤝 It's a draw!"
    else:
        verdict = f"🏆 <b>{names[winner]}</b> {cls.symbols[winner]} wins!"
    if "score" in result:
        verdict += f"\nFinal score: {cls.symbols[0]} {result['score'][0]} — {result['score'][1]} {cls.symbols[1]}"
    await query.answer()
    await _edit(
        query,
        f"{_header(cls, game)}\n\n{verdict}",
        _markup(cls, state, game["id"], frozen=True),
    )


async def game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, game_id, payload = query.data.split(":", 2)
    game_id = int(game_id)

    async with _locks[game_id]:
        game = db.get_game(game_id)
        if game is None:
            await query.answer("This game no longer exists.", show_alert=True)
            return
        cls = GAME_REGISTRY.get(game["game_type"])
        if cls is None:
            await query.answer("Unknown game type.", show_alert=True)
            return
        if payload == NOOP:
            await query.answer()
        elif game["status"] == "pending":
            await _handle_pending(query, game, cls, payload)
        elif game["status"] == "active":
            await _handle_move(query, game, cls, payload)
        else:
            await query.answer("This game is already over.")


def get_handlers():
    handlers = [
        CommandHandler("tictactoe", _make_start_handler("ttt")),
        CommandHandler("reversi", _make_start_handler("reversi")),
        CommandHandler("checkers", _make_start_handler("checkers")),
        CommandHandler("chess", _make_start_handler("chess")),
        CallbackQueryHandler(game_callback, pattern=r"^bg:\d+:"),
    ]
    return handlers
