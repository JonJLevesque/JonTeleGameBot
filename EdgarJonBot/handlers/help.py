from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import config

COMMAND_LIST = [
    ("idea", "save an idea (or reply to one)"),
    ("ideas", "the idea vault"),
    ("pick", "resurface a random idea"),
    ("shipped", "log something you shipped"),
    ("log", "recent shipping log"),
    ("recap", "this week's recap, on demand"),
    ("reminder", "remind you: /reminder in 2h push the fix"),
    ("reminders", "pending reminders"),
    ("remember", "store a fact by hand"),
    ("brain", "what the bot has picked up"),
    ("forget", "delete a fact by id"),
    ("tldr", "summarize a link"),
    ("settle", "settle an argument, decisively"),
    ("hottake", "a spicy tech opinion to fight about"),
    ("duck", "rubber duck session (/duck stop to end)"),
    ("help", "this"),
]

HELP = f"""\
<b>{config.BOT_NAME}</b> — the third dev in the chat.

Talk to me by name, @mention or reply. I listen to everything and quietly \
file away ideas and facts (see /brain, /ideas). Sundays I post a recap.

<b>Ideas</b>
/idea &lt;text&gt; — save it. /ideas — list. /pick — random one back.
/idea done &lt;id&gt; · /idea rm &lt;id&gt;

<b>Shipping</b>
/shipped &lt;what&gt; — log it. /log — recent. /recap — week so far.

<b>Reminders</b>
/reminder in 45m check the deploy · /reminder tomorrow 9am call Edgar
/reminders — pending · /reminder cancel &lt;id&gt;

<b>Brain</b>
I learn from whatever you say to me, on the spot — corrections replace old facts. \
Or be explicit: “remember Edgar's on the ledger branch”, “forget the postgres \
thing”, “forget everything about the mall”, “from now on, be shorter” (standing \
instruction — I'll obey until you /forget it).
/remember &lt;fact&gt; · /brain · /forget &lt;id|words|last|all&gt;

<b>Tools</b>
/tldr &lt;url&gt; · /settle &lt;the argument&gt; · /hottake [topic]
/duck — explain your bug, I only ask questions. /duck stop"""


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_html(HELP)


def get_handlers():
    return [CommandHandler(["help", "start"], help_cmd)]
