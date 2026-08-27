/** The Lobby: a free, public chat where the funnel starts. The bot greets newcomers with the
 *  pitch and a one-tap way into the DM funnel, answers /join, and otherwise stays quiet —
 *  no XP, drops, or games here (those belong to the paid room). */
import { InlineKeyboard, type Bot } from "grammy";
import type { Ctx } from "../../context";
import { esc } from "../../services/telegram";

function inLobby(ctx: Ctx): boolean {
  return !!ctx.chat && ctx.cfg.lobbyChatId !== 0 && ctx.chat.id === ctx.cfg.lobbyChatId;
}

function pitch(ctx: Ctx, name?: string): { text: string; kb: InlineKeyboard } {
  const c = ctx.cfg;
  const tiers = c.tiers.map((t) =>
    `${t.emoji} <b>${esc(t.name)}</b> ⭐${t.stars} / $${t.usd.toFixed(2)} — ${t.group ? `${esc(c.roomNames.feed)} + ${esc(c.roomNames.room)}` : esc(c.roomNames.feed)}`,
  ).join("\n");
  const hello = name ? `Welcome to ${esc(c.roomNames.lobby)}, ${esc(name)}. ` : "";
  const text = `${hello}This is the free room. The good stuff is behind the door:\n\n${tiers}\n\nTap below — it opens a private chat with me, takes a minute, and you're in.`;
  const kb = new InlineKeyboard().url(`🌸 Join ${esc(c.roomNames.feed)}`, `https://t.me/${ctx.me.username}?start=lobby`);
  return { text, kb };
}

export function registerLobby(bot: Bot<Ctx>) {
  // Greet newcomers. Registered before the membership module; always passes through.
  bot.on("chat_member", async (ctx, next) => {
    try {
      const upd = ctx.chatMember;
      if (inLobby(ctx) && !upd.new_chat_member.user.is_bot) {
        const inStatuses = ["member", "administrator", "creator"];
        const was = inStatuses.includes(upd.old_chat_member.status);
        const now = inStatuses.includes(upd.new_chat_member.status);
        if (!was && now) {
          const { text, kb } = pitch(ctx, upd.new_chat_member.user.first_name);
          await ctx.api.sendMessage(ctx.chat!.id, text, { parse_mode: "HTML", reply_markup: kb });
        }
      }
    } catch (e) { console.error("lobby welcome failed", String(e)); }
    await next();
  });

  bot.command(["join", "vip", "start"], async (ctx, next) => {
    if (!inLobby(ctx)) return next();
    const { text, kb } = pitch(ctx);
    await ctx.reply(text, { parse_mode: "HTML", reply_markup: kb, reply_parameters: { message_id: ctx.msg.message_id } });
  });
}
