"""/start and /help."""
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

HELP_TEXT = """\
🎉 <b>Party Bot</b> — games and cookies for your group chat

<b>Party games</b>
/truthordare — get a random truth or dare prompt
/wouldyourather — get a random "would you rather" dilemma
/paranoia [@user] — whisper a secret question to a player; they answer aloud, then flip the coin to see if it's revealed
/taboo — get a secret phrase and make the chat guess it in 3 clues, without using its key words (winner and describer earn a 🍪)
/roleplay — random scenario + random roles for chat members to act out
/spicymode on|off — admins: unlock Spicy🌶️ prompts for this chat

<b>Cookie economy</b> 🍪
/cookie @user — award a cookie (or reply to their message with /cookie)
/cookies [@user] — check a cookie balance (yours by default)
/cookieboard — top cookie holders in this chat
/shop — the IOU shop: add real-world rewards, buy them with cookies
/redeem id — cash cookies in for a reward (it goes on the record)

<b>Board games</b> (challenge with @user, by replying, or open to anyone;
add a number to wager cookies: /chess @rival 10 — winner takes the pot)
/tictactoe [@user] — Tic-Tac-Toe ❌⭕
/reversi [@user] — Reversi/Othello ⚫⚪
/checkers [@user] — Checkers 🔴⚪
/chess [@user] — Chess ♔♚ (castling, en passant, the lot)
Every board has 🏳️ Resign; finished boards offer a 🔄 Rematch.

<b>Tournaments &amp; trivia</b> 🌍
/beautiful — next head-to-head: 2000 places, two photos, you both vote;
winners advance until one place rules the world (status | reset)
/tournament Title: a, b, c — knockout bracket for ANY list (movies,
date ideas, baby names…), same two-vote rules
/whereami — mystery photo, guess the country, correct = 🍪
/settle the argument — the court rules, decisively (or reply with /settle)

<b>Daily rituals</b>
/wordle — the real NYT Wordle: I DM you the puzzle (or tap the Play
button), results auto-post to the group, fastest solver wins the day's 🍪
/dailyq on|now|off — one question a day for you both, and they get deeper
(and, with spicy mode, steamier) as the days go
/recap on|now|off — Sunday-evening scoreboard of the week

<b>Other</b>
/help — this message

Tip: I only learn who's in the chat when people send messages, so if
/cookie @someone says I don't know them, reply to their message instead.
"""

COMMAND_LIST = [
    ("truthordare", "Random truth or dare prompt"),
    ("wouldyourather", "Random would-you-rather dilemma"),
    ("paranoia", "Whisper a secret question to a player"),
    ("taboo", "Secret phrase, 3 clues, no forbidden words"),
    ("roleplay", "Random scenario + roles to act out"),
    ("spicymode", "Admins: toggle Spicy🌶️ prompts (on/off)"),
    ("cookie", "Award a cookie (@user or reply)"),
    ("cookies", "Check a cookie balance"),
    ("cookieboard", "Cookie leaderboard for this chat"),
    ("tictactoe", "Challenge someone to Tic-Tac-Toe"),
    ("reversi", "Challenge someone to Reversi"),
    ("checkers", "Challenge someone to Checkers"),
    ("chess", "Challenge someone to Chess"),
    ("beautiful", "World's Most Beautiful Place photo knockout"),
    ("wordle", "Daily NYT Wordle duel (DM me to play)"),
    ("dailyq", "Daily question ritual (on|now|off)"),
    ("tournament", "Knockout bracket for any list"),
    ("whereami", "Guess the country from a photo"),
    ("settle", "The court rules on your argument"),
    ("shop", "IOU shop: cookies for real rewards"),
    ("redeem", "Buy a shop reward with cookies"),
    ("recap", "Weekly Sunday scoreboard (on|now|off)"),
    ("help", "List all commands"),
]


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_html(HELP_TEXT)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Deep links: t.me/<bot>?start=wordle from the group's Play button.
    if (update.effective_chat.type == "private"
            and context.args and context.args[0] == "wordle"):
        from . import wordle
        await wordle.begin_from_start(update, context)
        return
    await help_command(update, context)


def get_handlers():
    return [
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
    ]
