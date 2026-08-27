"""/been and /map — everywhere you two have been, together, on one map. 🗺️

/been Lisbon | the tram ride — geocodes the place (OpenStreetMap), pins it.
/map renders every pin onto a real map image. /places bracket throws all of
them into a knockout tournament (two votes per matchup) to crown the best
trip — the running bracket of places you've been.
"""
import html
import io
import logging

import httpx
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import db
from . import tournament as tour
from .bracket import new_bracket, start_next_match
from .common import require_group

log = logging.getLogger("ajbot.places")
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "AJBot/1.0 (telegram couple bot; contact: jlevesque84@gmail.com)"


def parse_been(raw: str) -> tuple[str, str | None]:
    """'Lisbon | the tram ride' -> ('Lisbon', 'the tram ride')."""
    name, _, note = raw.partition("|")
    name = " ".join(name.split()).strip()[:80]
    note = " ".join(note.split()).strip()[:200] or None
    return name, note


async def geocode(query: str) -> tuple[str, float, float] | None:
    """(display name, lat, lon) via Nominatim, or None."""
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": UA}) as client:
            r = await client.get(NOMINATIM, params={"q": query, "format": "json", "limit": 1, "accept-language": "en"})
            r.raise_for_status()
            hits = r.json()
    except (httpx.HTTPError, ValueError):
        log.warning("geocode failed for %r", query)
        return None
    if not hits:
        return None
    h = hits[0]
    display = h.get("display_name", query)
    short = ", ".join(p.strip() for p in display.split(",")[:2])
    return short, float(h["lat"]), float(h["lon"])


def render_map(rows) -> bytes | None:
    try:
        import staticmaps
    except ImportError:
        return None
    ctx = staticmaps.Context()
    ctx.set_tile_provider(staticmaps.tile_provider_OSM)
    for r in rows:
        ctx.add_object(staticmaps.Marker(staticmaps.create_latlng(r["lat"], r["lon"]), color=staticmaps.RED, size=10))
    if len(rows) == 1:
        ctx.set_zoom(6)
    try:
        img = ctx.render_pillow(1000, 640)
    except Exception:
        log.exception("map render failed")
        return None
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


async def been_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    raw = " ".join(context.args or []).strip()
    if not raw or raw.lower() == "list":
        rows = db.places(chat_id)
        if not rows:
            await msg.reply_text("No pins yet. /been Lisbon | the tram ride — I'll find it and pin it.")
            return
        lines = [f"🗺️ <b>Been there</b> — {len(rows)} place{'s' if len(rows) != 1 else ''}"]
        for r in rows:
            note = f" — <i>{html.escape(r['note'])}</i>" if r["note"] else ""
            lines.append(f"📍 <b>{html.escape(r['display'])}</b>{note}")
        lines.append("\n/map to see them · /places bracket to rank them · /been remove <name>")
        await msg.reply_html("\n".join(lines))
        return
    if raw.lower().startswith("remove "):
        name = raw[7:].strip()
        await msg.reply_text("Unpinned." if db.place_remove(chat_id, name) else "No pin by that name — /been list shows them.")
        return
    name, note = parse_been(raw)
    if not name:
        await msg.reply_text("Where? /been Lisbon | the tram ride")
        return
    await context.bot.send_chat_action(chat_id, "find_location")
    hit = await geocode(name)
    if not hit:
        await msg.reply_text(f"I can't find “{name}” on any map I trust. Try a city, a landmark, or a fuller name.")
        return
    display, lat, lon = hit
    pid = db.place_add(chat_id, name, display, lat, lon, note, update.effective_user.first_name)
    if pid is None:
        await msg.reply_text(f"{display} is already on the map.")
        return
    n = len(db.places(chat_id))
    await msg.reply_html(
        f"📍 Pinned <b>{html.escape(display)}</b>" + (f" — <i>{html.escape(note)}</i>" if note else "") +
        f"\nThat's {n} on the map. /map to see it."
    )


async def map_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update):
        return
    chat_id = update.effective_chat.id
    rows = db.places(chat_id)
    if not rows:
        await update.effective_message.reply_text("The map is blank. /been <place> to start pinning.")
        return
    await context.bot.send_chat_action(chat_id, "upload_photo")
    png = render_map(rows)
    caption = f"🗺️ {len(rows)} place{'s' if len(rows) != 1 else ''} you've been, together."
    if png is None:
        await update.effective_message.reply_text(caption + " (Map rendering is unavailable right now — /been list has the pins.)")
        return
    await update.effective_message.reply_photo(png, caption=caption)


async def places_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/places bracket — knockout of everywhere you've been."""
    if not await require_group(update):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    sub = (context.args or [""])[0].lower()
    if sub != "bracket":
        await msg.reply_text("/places bracket — pit every pin against each other; two votes decide each matchup.")
        return
    rows = db.places(chat_id)
    if len(rows) < 2:
        await msg.reply_text("I need at least two pins for a bracket. /been <place> a couple of times first.")
        return
    state = db.get_tournament(chat_id)
    if state and state.get("champion") is None:
        await msg.reply_html(f"⚠️ <b>{html.escape(state['title'])}</b> is still running. Finish it or /tournament reset first.")
        return
    items = [r["display"] for r in rows][:tour.MAX_ITEMS]
    state = new_bracket(range(len(items)))
    state["items"] = items
    state["title"] = "Best trip ever"
    start_next_match(state)
    db.save_tournament(chat_id, state)
    await msg.reply_html(f"🏆 <b>Best trip ever</b> — {len(items)} destinations enter the bracket. Two votes decide each matchup.")
    await tour._post_match(chat_id, context, state)


def get_handlers():
    return [
        CommandHandler("been", been_cmd),
        CommandHandler("map", map_cmd),
        CommandHandler("places", places_cmd),
    ]
