from . import (
    battleship, beautiful, boardgames, brain, casino, cookies, dailydrops,
    dailyq, geo, help, iou, levels, museum, party, persona, pet, pigeon, places, quotes, recap, usquiz,
    roleplay, settle, shop, taboo, tournament, trivia, wordle,
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
        + iou.get_handlers()
        + places.get_handlers()
        + museum.get_handlers()
        + usquiz.get_handlers()
        + recap.get_handlers()
        + settle.get_handlers()
        + geo.get_handlers()
        + tournament.get_handlers()
        + trivia.get_handlers()
        + pigeon.get_handlers()
        + quotes.get_handlers()
        + battleship.get_handlers()
        + casino.get_handlers()
        + dailydrops.get_handlers()
        + levels.get_handlers()
        + pet.get_handlers()
        + persona.get_handlers()
        + brain.get_handlers()
    )


__all__ = ["all_handlers", "track_users"]
