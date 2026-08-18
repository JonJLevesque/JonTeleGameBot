from . import (
    beautiful, boardgames, cookies, dailyq, help, party, roleplay, shop,
    taboo, wordle,
)
from .common import track_users


def all_handlers():
    """All handler registrations. Entries are either a bare handler
    (added to PTB's default group 0) or a (handler, group) tuple."""
    return (
        help.get_handlers()
        + party.get_handlers()
        + roleplay.get_handlers()
        + taboo.get_handlers()
        + cookies.get_handlers()
        + boardgames.get_handlers()
        + beautiful.get_handlers()
        + wordle.get_handlers()
        + dailyq.get_handlers()
        + shop.get_handlers()
    )


__all__ = ["all_handlers", "track_users"]
