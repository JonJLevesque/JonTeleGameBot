"""/battleship — naval warfare with hidden fleets. 🚢

The one game only this bot's DM setup makes possible: both fleets are
placed secretly (auto-placed at accept time, then DM'd to their owners),
and all anyone sees in the group is each player's shot-map of the enemy
waters. Hidden per-player state and asymmetric views don't fit the
TwoPlayerBoardGame abstraction (which renders ONE shared board from ONE
shared state), so this is a standalone handler rather than a
GAME_REGISTRY entry — but it persists through the same `games` table,
uses the same stake escrow, and mirrors the same challenge flow, with
callback prefix "bs:" instead of "bg:".

Classic streak rules: a hit fires again, a miss passes the turn. First
to sink all four enemy ships (lengths 4, 3, 3, 2) wins the pot.
"""
import asyncio
import html
import json
import random
from collections import defaultdict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

import db
from games import NOOP
from .boardgames import _edit, _payout
from .common import require_group, target_from_message

SIZE = 8
FLEET = (4, 3, 3, 2)
SYMBOLS = ("🔵", "🔴")

_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


# ------------------------------------------------------------ pure game logic

def place_fleet(rng=random) -> list[list[int]]:
    """Random legal fleet: straight ships, in bounds, no overlaps. Ships may
    touch — forbidding adjacency would complicate the placer for little
    gameplay gain on an 8x8 board."""
    taken: set[int] = set()
    fleet = []
    for length in FLEET:
        while True:
            if rng.random() < 0.5:  # horizontal
                r = rng.randrange(SIZE)
                c = rng.randrange(SIZE - length + 1)
                cells = [r * SIZE + c + i for i in range(length)]
            else:
                r = rng.randrange(SIZE - length + 1)
                c = rng.randrange(SIZE)
                cells = [(r + i) * SIZE + c for i in range(length)]
            if not taken & set(cells):
                fleet.append(cells)
                taken.update(cells)
                break
    return fleet


def new_state() -> dict:
    """Fresh state; the challenger (player 0) fires first."""
    return {"turn": 0, "ships": [place_fleet(), place_fleet()],
            "shots": [[], []]}


def apply_shot(state: dict, player: int, cell: int):
    """Fire at a cell in the enemy waters. Returns an error string for an
    invalid shot (state unchanged), or {"hit": bool, "sunk": length|None}.
    A hit keeps the turn, a miss passes it; win detection is outcome()'s
    job. Also sets state["note"] for the status line."""
    if not 0 <= cell < SIZE * SIZE:
        return "That square is off the map."
    shots = state["shots"][player]
    if cell in shots:
        return "You already fired there!"
    shots.append(cell)
    for ship in state["ships"][1 - player]:
        if cell in ship:
            if all(c in shots for c in ship):
                state["note"] = f"☠️ Sunk a ship of length {len(ship)}!"
                return {"hit": True, "sunk": len(ship)}
            state["note"] = "💥 Hit!"
            return {"hit": True, "sunk": None}
    state["turn"] = 1 - player
    state["note"] = "🌊 Miss."
    return {"hit": False, "sunk": None}


def outcome(state: dict) -> dict | None:
    """None while both fleets float, else {"winner": 0|1}. Battleship has
    no draws."""
    for p in (0, 1):
        enemy = {c for ship in state["ships"][1 - p] for c in ship}
        if enemy <= set(state["shots"][p]):
            return {"winner": p}
    return None


# ------------------------------------------------------------------ rendering

def _shot_grid(state: dict, player: int) -> str:
    """`player`'s view of the enemy waters: ⬜ unknown, 💥 hit, 🌊 miss."""
    shots = set(state["shots"][player])
    enemy = {c for ship in state["ships"][1 - player] for c in ship}
    lines = []
    for r in range(SIZE):
        row = []
        for c in range(SIZE):
            i = r * SIZE + c
            if i in shots:
                row.append("💥" if i in enemy else "🌊")
            else:
                row.append("⬜")
        lines.append("".join(row))
    return "\n".join(lines)


def _sunk_count(state: dict, player: int) -> int:
    shots = set(state["shots"][player])
    return sum(1 for ship in state["ships"][1 - player]
               if set(ship) <= shots)


def _header(game) -> str:
    text = (
        f"🚢 <b>Battleship</b>\n"
        f"{SYMBOLS[0]} {html.escape(game['p0_name'])} vs "
        f"{SYMBOLS[1]} {html.escape(game['p1_name'] or '?')}"
    )
    if game["stake"]:
        text += f"\n💰 Pot: {game['stake'] * 2} 🍪"
    return text


def _board_text(game, state: dict, footer: str) -> str:
    names = (html.escape(game["p0_name"]), html.escape(game["p1_name"]))
    parts = [_header(game)]
    for p in (0, 1):
        parts.append(
            f"\n<b>{names[p]}'s shots</b> "
            f"({_sunk_count(state, p)}/{len(FLEET)} ships sunk)\n"
            f"{_shot_grid(state, p)}"
        )
    parts.append(f"\n{footer}")
    return "\n".join(parts)


def _turn_footer(game, state: dict) -> str:
    names = (html.escape(game["p0_name"]), html.escape(game["p1_name"]))
    line = (f"Turn: {SYMBOLS[state['turn']]} {names[state['turn']]} — "
            f"tap a square to fire!")
    if state.get("note"):
        line = f"{state['note']}\n{line}"
    return line


def _keyboard(state: dict, game_id: int,
              frozen: bool = False) -> InlineKeyboardMarkup:
    """The current player's 8x8 aiming grid. Already-shot squares are inert."""
    shots = set(state["shots"][state["turn"]])
    enemy = {c for ship in state["ships"][1 - state["turn"]] for c in ship}
    rows = []
    for r in range(SIZE):
        row = []
        for c in range(SIZE):
            i = r * SIZE + c
            if i in shots:
                label, payload = ("💥" if i in enemy else "🌊"), NOOP
            else:
                label, payload = "·", str(i)
            row.append(InlineKeyboardButton(
                label, callback_data=f"bs:{game_id}:{NOOP if frozen else payload}",
            ))
        rows.append(row)
    if frozen:
        rows.append([InlineKeyboardButton(
            "🔄 Rematch", callback_data=f"bs:{game_id}:rm")])
    else:
        rows.append([InlineKeyboardButton(
            "🏳️ Resign", callback_data=f"bs:{game_id}:rz")])
    return InlineKeyboardMarkup(rows)


async def _dm_fleets(context: ContextTypes.DEFAULT_TYPE, game, state: dict):
    """Best-effort: show each admiral their own fleet. A closed DM is fine —
    you don't need to know your own layout to fire at the enemy's."""
    for idx, uid in ((0, game["p0_id"]), (1, game["p1_id"])):
        cells = {c for ship in state["ships"][idx] for c in ship}
        grid = "\n".join(
            "".join("🚢" if r * SIZE + c in cells else "🌊"
                    for c in range(SIZE))
            for r in range(SIZE)
        )
        try:
            await context.bot.send_message(
                uid,
                f"🚢 Your fleet for game #{game['id']} — don't show anyone!\n"
                f"{grid}",
            )
        except TelegramError:
            pass


# ------------------------------------------------------------------- handlers

async def battleship_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
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
    stake = next((int(a) for a in (context.args or []) if a.isdecimal()), 0)
    if stake:
        have = db.get_cookies(update.effective_chat.id, challenger.id)
        if have < stake:
            await update.effective_message.reply_text(
                f"You only have {have} 🍪 — you can't stake {stake}."
            )
            return

    game_id = db.create_game(
        update.effective_chat.id, "battleship", challenger.id,
        challenger.first_name, opp_id, opp_name, stake=stake,
    )
    who = f"<b>{html.escape(opp_name)}</b>" if opp_id else "anyone brave enough"
    wager = f"\n💰 Stake: {stake} 🍪 each — winner takes all!" if stake else ""
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept", callback_data=f"bs:{game_id}:a"),
        InlineKeyboardButton("❌ Decline", callback_data=f"bs:{game_id}:d"),
    ]])
    challenger_name = html.escape(challenger.first_name)
    msg = await update.effective_message.reply_html(
        f"🚢 <b>Battleship</b>\n"
        f"<b>{challenger_name}</b> challenges {who}!{wager}\n"
        f"I place both fleets in secret and DM you yours.\n"
        f"({challenger_name} can tap Decline to cancel.)",
        reply_markup=keyboard,
    )
    db.set_game_message(game_id, msg.message_id)


async def _handle_pending(query, game, payload, context):
    user = query.from_user
    open_challenge = game["p1_id"] is None

    if payload == "a":
        if user.id == game["p0_id"]:
            await query.answer("You can't accept your own challenge!")
            return
        if not open_challenge and user.id != game["p1_id"]:
            await query.answer(f"This challenge is for {game['p1_name']}.")
            return
        if not db.escrow_and_activate(game, user.id, user.first_name,
                                      new_state()):
            await query.answer(
                f"One of you no longer has the {game['stake']} 🍪 stake — "
                f"the wager can't be covered.", show_alert=True)
            return
        game = db.get_game(game["id"])
        state = json.loads(game["state"])
        await query.answer("Fleets deployed — check your DMs!")
        await _dm_fleets(context, game, state)
        await _edit(
            query,
            _board_text(game, state, _turn_footer(game, state)),
            _keyboard(state, game["id"]),
        )
    elif payload == "d":
        if user.id == game["p0_id"]:
            text = (f"🚢 Battleship: challenge cancelled by "
                    f"{html.escape(game['p0_name'])}.")
        elif not open_challenge and user.id == game["p1_id"]:
            text = (f"🚢 Battleship: {html.escape(user.first_name)} "
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


async def _handle_move(query, game, payload):
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
    if not payload.isdecimal():
        await query.answer()
        return

    result = apply_shot(state, player, int(payload))
    if isinstance(result, str):
        await query.answer(result)
        return
    state.pop("_rz", None)  # a real shot cancels a pending resign confirmation

    names = (html.escape(game["p0_name"]), html.escape(game["p1_name"]))
    win = outcome(state)
    if win is None:
        db.update_game(game["id"], state=state)
        await query.answer(state.get("note", ""))
        await _edit(
            query,
            _board_text(game, state, _turn_footer(game, state)),
            _keyboard(state, game["id"]),
        )
        return

    db.update_game(game["id"], state=state, status="finished")
    winner = win["winner"]
    verdict = (
        f"☠️ Fleet destroyed! <b>{names[winner]}</b> {SYMBOLS[winner]} "
        f"rules the waves!"
    ) + _payout(game, winner)
    await query.answer("☠️ Victory!")
    await _edit(
        query,
        _board_text(game, state, verdict),
        _keyboard(state, game["id"], frozen=True),
    )


async def _handle_resign(query, game):
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
            "Really strike your colors? Tap 🏳️ again to confirm.",
            show_alert=True,
        )
        return
    winner = 1 - player
    names = (html.escape(game["p0_name"]), html.escape(game["p1_name"]))
    db.update_game(game["id"], state=state, status="finished")
    verdict = (
        f"🏳️ <b>{names[player]}</b> scuttles the fleet — "
        f"<b>{names[winner]}</b> {SYMBOLS[winner]} rules the waves!"
    ) + _payout(game, winner)
    await query.answer()
    await _edit(
        query,
        _board_text(game, state, verdict),
        _keyboard(state, game["id"], frozen=True),
    )


async def _handle_rematch(query, game, context):
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
        game["chat_id"], "battleship", user.id, user.first_name,
        opp_id, opp_name, stake=stake,
    )
    wager = f"\n💰 Stake: {stake} 🍪 each — winner takes all!" if stake else ""
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept", callback_data=f"bs:{game_id}:a"),
        InlineKeyboardButton("❌ Decline", callback_data=f"bs:{game_id}:d"),
    ]])
    msg = await context.bot.send_message(
        game["chat_id"],
        f"🔄 <b>Battleship rematch!</b>\n"
        f"<b>{html.escape(user.first_name)}</b> challenges "
        f"<b>{html.escape(opp_name)}</b>!{wager}",
        parse_mode="HTML", reply_markup=keyboard,
    )
    db.set_game_message(game_id, msg.message_id)
    await query.answer("Rematch challenge sent!")


async def battleship_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, game_id, payload = query.data.split(":", 2)
    game_id = int(game_id)

    async with _locks[game_id]:
        game = db.get_game(game_id)
        if game is None or game["game_type"] != "battleship":
            await query.answer("This game no longer exists.", show_alert=True)
            return
        if payload == NOOP:
            await query.answer()
        elif payload == "rm" and game["status"] == "finished":
            await _handle_rematch(query, game, context)
        elif game["status"] == "pending":
            await _handle_pending(query, game, payload, context)
        elif game["status"] == "active":
            if payload == "rz":
                await _handle_resign(query, game)
            else:
                await _handle_move(query, game, payload)
        else:
            await query.answer("This game is already over.")


def get_handlers():
    return [
        CommandHandler("battleship", battleship_cmd),
        CallbackQueryHandler(battleship_callback, pattern=r"^bs:\d+:"),
    ]
