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
/daily — claim your daily cookies; consecutive days pay more 🔥
/shop — the IOU shop: add real-world rewards, buy them with cookies
/redeem id — cash cookies in for a reward (it becomes an IOU on the record)
/iou @user a coffee — they owe you · /iou owe @user dinner — you owe them
/ious — the open ledger · /iou paid id · /iou nudge id · /iou cancel id
Watch the skies: supply crates 🎁 drop when the chat is lively —
first tap keeps the contents. Usually.

<b>The casino</b> 🎰
/slots stake — Telegram itself spins the reels; 7️⃣7️⃣7️⃣ pays 10x
/blackjack stake — hit, stand or double against the house (3:2 on 21)

<b>Board games</b> (challenge with @user, by replying, or open to anyone;
add a number to wager cookies: /chess @rival 10 — winner takes the pot)
/tictactoe [@user] — Tic-Tac-Toe ❌⭕
/reversi [@user] — Reversi/Othello ⚫⚪
/checkers [@user] — Checkers 🔴⚪
/chess [@user] — Chess ♔♚ (castling, en passant, the lot)
/battleship [@user] — Battleship 🚢: hidden fleets, 💥 keeps your turn
Every board has 🏳️ Resign; finished boards offer a 🔄 Rematch.

<b>Tournaments &amp; trivia</b> 🌍
/beautiful — next head-to-head: 2000 places, two photos, you both vote;
winners advance until one place rules the world (status | reset)
/tournament Title: a, b, c — knockout bracket for ANY list (movies,
date ideas, baby names…), same two-vote rules
/trivia [topic] — quiz poll: correct answers earn 🍪, fastest gets
a bonus (name a topic and the question obliges)
/whereami — mystery photo, guess the country, correct = 🍪
/settle the argument — the court rules, decisively (or reply with /settle)

<b>Daily rituals</b>
/wordle — the real NYT Wordle: I DM you the puzzle (or tap the Play
button), results auto-post to the group, fastest solver wins the day's 🍪
/dailyq on|now|off — one question a day for you both, and they get deeper
(and, with spicy mode, steamier) as the days go
/recap on|now|off — Sunday-evening scoreboard of the week

<b>Carrier pigeon</b> 🕊️
/tell — DM me something for someone in your group and I deliver it to
them, word for word, so you don't have to say it directly — now, or
later (/tell Jon in 2h…, at 9pm…, tomorrow 8am…)
/capsule — DM me a sealed time capsule (/capsule Jon 6mo …); no
duration and it arrives months from now, when they least expect it
/inbox — collect whispers waiting for you (DM me)

<b>The archives</b> 📜
/quote — reply to a legendary message to preserve it forever
/memory [word] — resurface a random archived quote

<b>Household</b> 🏠
/pet — the chat's shared pet: adopt it, feed it (1 🍪), play with it,
adore it, walk it, wash it, train it tricks (1 🍪), spoil it (/pet treat, 2 🍪),
tuck it in (/pet sleep), talk to it (/pet talk hi — it talks back once
it's hatched), see who parents hardest (/pet parents), and do
NOT let it starve — it will leave, and it will be dramatic
/level — this chat's shared relationship level; everything you two do
together feeds it

<b>Other</b>
/help — this message
Also: reply to me or @mention me and I'll answer. I have opinions,
and I remember things — tell me "remember …" and it's filed.
/memories — everything I know about you two (transparency policy)
/forget id — make me unknow one of them (also /forget 7 13, /forget last,
/forget all, or just tell me: “forget everything about the mall”)

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
    ("daily", "Claim your daily cookies — streaks pay more"),
    ("slots", "🎰 Spin for cookies (Telegram rolls the reels)"),
    ("blackjack", "Blackjack vs the house — 3:2 on 21"),
    ("pet", "The chat's shared pet — feed it, talk to it 🐣"),
    ("level", "The chat's shared relationship level 💞"),
    ("memories", "Everything the bot knows about you 🧠"),
    ("forget", "Delete memories: id(s), words, last, or all"),
    ("tictactoe", "Challenge someone to Tic-Tac-Toe"),
    ("reversi", "Challenge someone to Reversi"),
    ("checkers", "Challenge someone to Checkers"),
    ("chess", "Challenge someone to Chess"),
    ("trivia", "Quiz poll — correct answers earn 🍪 🧠"),
    ("beautiful", "World's Most Beautiful Place photo knockout"),
    ("wordle", "Daily NYT Wordle duel (DM me to play)"),
    ("dailyq", "Daily question ritual (on|now|off)"),
    ("tournament", "Knockout bracket for any list"),
    ("whereami", "Guess the country from a photo"),
    ("settle", "The court rules on your argument"),
    ("shop", "IOU shop: cookies for real rewards"),
    ("redeem", "Buy a shop reward with cookies"),
    ("iou", "Put a debt on the record"),
    ("ious", "Who owes whom what"),
    ("recap", "Weekly Sunday scoreboard (on|now|off)"),
    ("tell", "DM me a message; I deliver it for you 🕊️"),
    ("capsule", "Seal a time capsule for months from now 📜"),
    ("inbox", "Collect whispers waiting for you"),
    ("quote", "Reply to a message to archive it forever"),
    ("memory", "Resurface a random archived quote"),
    ("battleship", "Sink the hidden fleet 🚢"),
    ("help", "List all commands"),
]


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_html(HELP_TEXT)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from . import pigeon

    # Deep links: t.me/<bot>?start=<arg> from the group's inline buttons.
    if update.effective_chat.type == "private":
        arg = context.args[0] if context.args else None
        if arg == "wordle":
            from . import wordle
            await wordle.begin_from_start(update, context)
        elif arg == "inbox":
            await pigeon.inbox_from_start(update, context)
        elif arg == "tell":
            await pigeon.tell_from_start(update, context)
        else:
            await help_command(update, context)
        # Opening a DM is the moment undelivered whispers become deliverable.
        if arg != "inbox":
            await pigeon.flush_inbox(context, update.effective_user.id)
        return
    await help_command(update, context)


def get_handlers():
    return [
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
    ]
