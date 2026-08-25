"""Shared helpers."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update


def _local_tz():
    try:
        path = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in path:
            return ZoneInfo(path.split("zoneinfo/", 1)[1])
    except Exception:
        pass
    return datetime.now().astimezone().tzinfo


LOCAL_TZ = _local_tz()


def arg_text(update: Update) -> str:
    """Everything after the command, or the replied-to message's text."""
    msg = update.effective_message
    text = msg.text or ""
    rest = text.split(maxsplit=1)[1].strip() if " " in text.strip() else ""
    if not rest and msg.reply_to_message:
        rest = (msg.reply_to_message.text or msg.reply_to_message.caption or "").strip()
    return rest


def fmt_when(ts: float) -> str:
    return datetime.fromtimestamp(ts, LOCAL_TZ).strftime("%a %b %-d, %-H:%M")
