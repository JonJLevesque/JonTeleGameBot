"""/start and /help."""
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

HELP_TEXT = """\
🎉 <b>Party Bot</b> — games and cookies for your group chat

<b>Party games</b>
/truthordare — get a random truth or dare prompt
/wouldyourather — get a random "would you rather" dilemma
/paranoia [@user] — whisper a secret question to a player; they answer aloud, then flip the coin to see if it's revealed
/taboo — get a secret phrase and make the chat guess it in 3 clues, without using its words (winner and describer earn a 🍪)
/roleplay — random scenario + random roles for chat members to act out
/spicymode on|off — admins: unlock 18+ prompts for this chat

<b>Cookie economy</b> 🍪
/cookie @user — award a cookie (or reply to their message with /cookie)
/cookies [@user] — check a cookie balance (yours by default)
/cookieboard — top cookie holders in this chat

<b>Board games</b> (challenge with @user, by replying, or open to anyone)
/tictactoe [@user] — Tic-Tac-Toe ❌⭕
/reversi [@user] — Reversi/Othello ⚫⚪
/checkers [@user] — Checkers 🔴⚪

<b>World's Most Beautiful Place</b> 🌍
/beautiful — next head-to-head: 2000 places, two photos, you both vote;
winners advance until one place rules the world (status | reset)

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
    ("spicymode", "Admins: toggle 18+ prompts (on/off)"),
    ("cookie", "Award a cookie (@user or reply)"),
    ("cookies", "Check a cookie balance"),
    ("cookieboard", "Cookie leaderboard for this chat"),
    ("tictactoe", "Challenge someone to Tic-Tac-Toe"),
    ("reversi", "Challenge someone to Reversi"),
    ("checkers", "Challenge someone to Checkers"),
    ("beautiful", "World's Most Beautiful Place photo knockout"),
    ("help", "List all commands"),
]


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_html(HELP_TEXT)


def get_handlers():
    return [
        CommandHandler("start", help_command),
        CommandHandler("help", help_command),
    ]
