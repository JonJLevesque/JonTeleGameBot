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
import html
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
    if frozen:
        rows.append([InlineKeyboardButton(
            "🔄 Rematch", callback_data=f"bg:{game_id}:rm")])
    else:
        rows.append([InlineKeyboardButton(
            "🏳️ Resign", callback_data=f"bg:{game_id}:rz")])
    return InlineKeyboardMarkup(rows)


def _header(cls, game) -> str:
    text = (
        f"🎮 <b>{cls.name}</b>\n"
        f"{cls.symbols[0]} {html.escape(game['p0_name'])} vs "
        f"{cls.symbols[1]} {html.escape(game['p1_name'] or '?')}"
    )
    if game["stake"]:
        text += f"\n💰 Pot: {game['stake'] * 2} 🍪"
    return text


def _payout(game, winner: int | None) -> str:
    """Settle an escrowed pot. Returns a line for the verdict (or '')."""
    stake = game["stake"]
    if not stake:
        return ""
    if winner is None:
        db.add_cookies(game["chat_id"], game["p0_id"], stake, "wager refund")
        db.add_cookies(game["chat_id"], game["p1_id"], stake, "wager refund")
        return f"\n💰 Draw — both stakes of {stake} 🍪 refunded."
    winner_id = game["p0_id"] if winner == 0 else game["p1_id"]
    total = db.add_cookies(game["chat_id"], winner_id, stake * 2, "wager won")
    return f"\n💰 Winner takes the pot: +{stake * 2} 🍪 (now {total})."


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
        stake = next(
            (int(a) for a in (context.args or []) if a.isdecimal()), 0
        )
        if stake:
            have = db.get_cookies(update.effective_chat.id, challenger.id)
            if have < stake:
                await update.effective_message.reply_text(
                    f"You only have {have} 🍪 — you can't stake {stake}."
                )
                return

        game_id = db.create_game(
            update.effective_chat.id, code, challenger.id, challenger.first_name,
            opp_id, opp_name, stake=stake,
        )
        who = f"<b>{html.escape(opp_name)}</b>" if opp_id else "anyone brave enough"
        wager = f"\n💰 Stake: {stake} 🍪 each — winner takes all!" if stake else ""
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Accept", callback_data=f"bg:{game_id}:a"),
            InlineKeyboardButton("❌ Decline", callback_data=f"bg:{game_id}:d"),
        ]])
        challenger_name = html.escape(challenger.first_name)
        msg = await update.effective_message.reply_html(
            f"🎮 <b>{cls.name}</b>\n"
            f"<b>{challenger_name}</b> challenges {who}!{wager}\n"
            f"({challenger_name} can tap Decline to cancel.)",
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
        # Escrow both stakes and activate in one transaction; the pot pays
        # out when the game ends.
        if not db.escrow_and_activate(game, user.id, user.first_name,
                                      cls.new_state()):
            await query.answer(
                f"One of you no longer has the {game['stake']} 🍪 stake — "
                f"the wager can't be covered.", show_alert=True)
            return
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
            text = (f"🎮 {cls.name}: challenge cancelled by "
                    f"{html.escape(game['p0_name'])}.")
        elif not open_challenge and user.id == game["p1_id"]:
            text = (f"🎮 {cls.name}: {html.escape(user.first_name)} "
                    f"declined the challenge.")
        elif open_challenge:
            await query.answer(
                f"Anyone can Accept — only {game['p0_name']} can cancel this."
            )
            return
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
    state.pop("_rz", None)  # a real move cancels a pending resign confirmation

    names = (html.escape(game["p0_name"]), html.escape(game["p1_name"]))
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
    verdict += _payout(game, winner)
    await query.answer()
    await _edit(
        query,
        f"{_header(cls, game)}\n\n{verdict}",
        _markup(cls, state, game["id"], frozen=True),
    )


async def _handle_resign(query, game, cls):
    user = query.from_user
    players = (game["p0_id"], game["p1_id"])
    if user.id not in players:
        await query.answer("You're not in this game!")
        return
    player = players.index(user.id)
    state = json.loads(game["state"])
    if state.get("_rz") != player:
        state["_rz"] = player
        db.update_game(game["id"], state=state)
        await query.answer(
            "Really resign? Tap 🏳️ again to confirm.", show_alert=True
        )
        return
    winner = 1 - player
    names = (html.escape(game["p0_name"]), html.escape(game["p1_name"]))
    state["sel"] = None
    db.update_game(game["id"], state=state, status="finished")
    verdict = (
        f"🏳️ <b>{names[player]}</b> resigns — "
        f"<b>{names[winner]}</b> {cls.symbols[winner]} wins!"
    ) + _payout(game, winner)
    await query.answer()
    await _edit(
        query,
        f"{_header(cls, game)}\n\n{verdict}",
        _markup(cls, state, game["id"], frozen=True),
    )


async def _handle_rematch(query, game, cls, context):
    user = query.from_user
    players = (game["p0_id"], game["p1_id"])
    if user.id not in players or game["p1_id"] is None:
        await query.answer("Only the players can call a rematch!")
        return
    other = 1 - players.index(user.id)
    opp_id = players[other]
    opp_name = (game["p0_name"], game["p1_name"])[other]
    stake = game["stake"]
    if stake and db.get_cookies(game["chat_id"], user.id) < stake:
        await query.answer(
            f"You don't have {stake} 🍪 to re-stake.", show_alert=True)
        return
    game_id = db.create_game(
        game["chat_id"], game["game_type"], user.id, user.first_name,
        opp_id, opp_name, stake=stake,
    )
    wager = f"\n💰 Stake: {stake} 🍪 each — winner takes all!" if stake else ""
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept", callback_data=f"bg:{game_id}:a"),
        InlineKeyboardButton("❌ Decline", callback_data=f"bg:{game_id}:d"),
    ]])
    msg = await context.bot.send_message(
        game["chat_id"],
        f"🔄 <b>{cls.name} rematch!</b>\n"
        f"<b>{html.escape(user.first_name)}</b> challenges "
        f"<b>{html.escape(opp_name)}</b>!{wager}",
        parse_mode="HTML", reply_markup=keyboard,
    )
    db.set_game_message(game_id, msg.message_id)
    await query.answer("Rematch challenge sent!")


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
        elif payload == "rm" and game["status"] == "finished":
            await _handle_rematch(query, game, cls, context)
        elif game["status"] == "pending":
            await _handle_pending(query, game, cls, payload)
        elif game["status"] == "active":
            if payload == "rz":
                await _handle_resign(query, game, cls)
            else:
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
