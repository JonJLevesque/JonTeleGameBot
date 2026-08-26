/** Shop: /shop listing + buy callback, title follow-up DM, admin item + queue commands. */
import { tierAllowsGroup } from "../../config";
import type { Bot } from "grammy";
import { InlineKeyboard } from "grammy";
import type { Ctx } from "../../context";
import { audit } from "../../db";
import { signCb, verifyCb } from "../../domain/callbacks";
import { getXp } from "../../services/ledger";
import { ephemeral, esc } from "../../services/telegram";
import { inDm, inGroup, membershipOf, threadOf } from "../games/common";
import {
  applyPendingTitle, discountedPrice, fulfillOrder, itemByCode, listItems, meetsTier, openQueue, purchase, refundOrder,
  seedDefaultItems,
} from "./core";

export { refundStaleOrders, expireTitles, seedDefaultItems } from "./core";

async function say(ctx: Ctx, text: string, kb?: InlineKeyboard) {
  if (inDm(ctx)) { await ctx.reply(text, { parse_mode: "HTML", reply_markup: kb }); return; }
  if (!ctx.chat || !ctx.from) return;
  if (kb) {
    await ctx.api.raw.sendMessage({ chat_id: ctx.chat.id, receiver_user_id: ctx.from.id, text, parse_mode: "HTML", reply_markup: kb, message_thread_id: threadOf(ctx) })
      .catch((e) => console.warn("ephemeral shop failed", String(e)));
  } else {
    await ephemeral(ctx.api, ctx.chat.id, ctx.from.id, text, { threadId: threadOf(ctx) });
  }
}

/** Parses `add <code> "<name>" <price> auto|queue [min_tier] [desc...]`. */
export function parseShopAdd(s: string): { code: string; name: string; price: number; fulfillment: "auto" | "queue"; minTier: string | null; desc: string | null } | null {
  const m = s.match(/^(\S+)\s+"([^"]+)"\s+(\d+)\s+(auto|queue)(?:\s+(\S+))?(?:\s+(.+))?$/s);
  if (!m) return null;
  const [, code, name, price, fulfillment, minTier, desc] = m;
  return { code: code!.toLowerCase(), name: name!, price: Number(price), fulfillment: fulfillment as "auto" | "queue", minTier: minTier && minTier !== "-" ? minTier : null, desc: desc?.trim() ?? null };
}

export function registerShop(bot: Bot<Ctx>) {
  // ---- /shop (member listing and admin management) ----
  bot.command("shop", async (ctx, next) => {
    if (!ctx.from || !(inDm(ctx) || inGroup(ctx))) return next();
    const { env, cfg } = ctx;
    const raw = (ctx.match?.toString() ?? "").trim();
    const [sub] = raw.split(/\s+/);

    if (ctx.isAdmin && inDm(ctx) && (sub === "add" || sub === "edit" || sub === "rm")) {
      const tail = raw.slice(sub.length).trim();
      if (sub === "add") {
        const p = parseShopAdd(tail);
        if (!p) return say(ctx, 'Format: /shop add &lt;code&gt; "&lt;name&gt;" &lt;price&gt; auto|queue [min_tier|-] [description]');
        if (p.price <= 0) return say(ctx, "Price must be positive.");
        if (p.minTier && !cfg.tiers.some((t) => t.code === p.minTier)) return say(ctx, `Unknown tier "${esc(p.minTier)}". Tiers: ${cfg.tiers.map((t) => t.code).join(", ")}`);
        await env.DB.prepare(
          `INSERT INTO shop_items (code, name, description, price, fulfillment, min_tier, enabled) VALUES (?, ?, ?, ?, ?, ?, 1)
           ON CONFLICT (code) DO UPDATE SET name = excluded.name, description = excluded.description, price = excluded.price, fulfillment = excluded.fulfillment, min_tier = excluded.min_tier, enabled = 1`,
        ).bind(p.code, p.name, p.desc, p.price, p.fulfillment, p.minTier).run();
        await audit(env, ctx.from.id, "shop.item.add", p.code, p);
        return say(ctx, `Saved <b>${esc(p.name)}</b> (${esc(p.code)}) at ${p.price}.`);
      }
      if (sub === "edit") {
        const m = tail.match(/^(\S+)\s+(price|name|enabled|desc)\s+(.+)$/s);
        if (!m) return say(ctx, "Format: /shop edit &lt;code&gt; price|name|enabled|desc &lt;value&gt;");
        const [, code, field, value] = m as [string, string, "price" | "name" | "enabled" | "desc", string];
        const item = await itemByCode(env, code.toLowerCase());
        if (!item) return say(ctx, `No item "${esc(code)}".`);
        let sql: string; let v: string | number;
        switch (field) {
          case "price": v = Number(value); if (!Number.isInteger(v) || v <= 0) return say(ctx, "Price must be a positive integer."); sql = "price = ?"; break;
          case "name": v = value.trim(); sql = "name = ?"; break;
          case "desc": v = value.trim(); sql = "description = ?"; break;
          case "enabled": v = /^(1|true|yes|on)$/i.test(value.trim()) ? 1 : 0; sql = "enabled = ?"; break;
        }
        await env.DB.prepare(`UPDATE shop_items SET ${sql} WHERE id = ?`).bind(v, item.id).run();
        await audit(env, ctx.from.id, "shop.item.edit", code, { field, value: v });
        return say(ctx, `Updated ${esc(code)}.${field} → ${esc(String(v))}.`);
      }
      // rm: disable rather than delete so past purchases keep their item row
      const code = tail.split(/\s+/)[0]?.toLowerCase();
      if (!code) return say(ctx, "Format: /shop rm &lt;code&gt;");
      const r = await env.DB.prepare("UPDATE shop_items SET enabled = 0 WHERE code = ?").bind(code).run();
      await audit(env, ctx.from.id, "shop.item.rm", code);
      return say(ctx, (r.meta.changes ?? 0) > 0 ? `Removed ${esc(code)} from the shop.` : `No item "${esc(code)}".`);
    }

    // listing
    await seedDefaultItems(env);
    const items = await listItems(env);
    if (items.length === 0) return say(ctx, "The shop is empty right now.");
    const m = await membershipOf(env, ctx.from.id);
    if (!m || !(m.state === "active" || m.state === "grace")) return say(ctx, "You're not a member yet — /start to join. 🌸");
    if (!tierAllowsGroup(cfg, m.tier)) {
      const up = cfg.tiers.find((t) => t.group);
      return say(ctx, `The shop is part of the room. ${up ? `${up.emoji} Upgrade to ${up.name} — /start` : ""}`);
    }
    const { level } = await getXp(env, ctx.from.id);
    const disc = level > 0 ? discountedPrice(100, level) : 100;
    const kb = new InlineKeyboard();
    const lines: string[] = [`🛍 <b>${esc(cfg.communityName)} shop</b>${disc < 100 ? ` — level ${level} discount ${100 - disc}%` : ""}`];
    let i = 0;
    for (const it of items) {
      const price = discountedPrice(it.price, level);
      const locked = !meetsTier(cfg, it, m?.tier ?? null);
      const tierTag = it.min_tier ? ` (${cfg.tiers.find((t) => t.code === it.min_tier)?.name ?? it.min_tier}+)` : "";
      lines.push(`${locked ? "🔒" : "•"} <b>${esc(it.name)}</b> — ${price} ${cfg.pointsEmoji}${tierTag}${it.description ? `\n   <i>${esc(it.description)}</i>` : ""}`);
      if (!locked) {
        kb.text(`${it.name} · ${price}`, await signCb(env.CALLBACK_HMAC_KEY, "buy", String(it.id)));
        if (++i % 2 === 0) kb.row();
      }
    }
    if (ctx.isAdmin && inDm(ctx)) lines.push("\nAdmin: /shop add|edit|rm · /queue");
    await say(ctx, lines.join("\n"), kb);
  });

  // ---- buy callback ----
  bot.on("callback_query:data", async (ctx, next) => {
    const v = await verifyCb(ctx.env.CALLBACK_HMAC_KEY, ctx.callbackQuery.data);
    if (!v || v.kind !== "buy") return next();
    const itemId = Number(v.payload);
    if (!Number.isFinite(itemId)) return ctx.answerCallbackQuery();
    const r = await purchase(ctx.env, ctx.cfg, ctx.api, { id: ctx.from.id, first_name: ctx.from.first_name, username: ctx.from.username }, itemId, ctx.callbackQuery.id);
    if (!r.ok) return ctx.answerCallbackQuery({ text: r.message, show_alert: r.reason === "insufficient" });
    const text = `✅ Bought <b>${esc(r.item.name)}</b> for ${r.price} ${ctx.cfg.pointsEmoji}. Balance: ${r.balance}.\n${r.message}`;
    if (ctx.chat?.type === "private") { await ctx.answerCallbackQuery({ text: "Done" }); await ctx.reply(text, { parse_mode: "HTML" }); }
    else if (ctx.chat) await ephemeral(ctx.api, ctx.chat.id, ctx.from.id, text, { callbackQueryId: ctx.callbackQuery.id });
    else await ctx.answerCallbackQuery({ text: `Bought ${r.item.name}.` });
  });

  // ---- title7d follow-up: next DM text while pending_title:<uid> is set ----
  bot.on("message:text", async (ctx, next) => {
    if (!inDm(ctx) || !ctx.from || ctx.message.text.startsWith("/")) return next();
    const res = await applyPendingTitle(ctx.env, ctx.cfg, ctx.api, ctx.from.id, ctx.message.text);
    if (res === null) return next();
    await ctx.reply(res, { parse_mode: "HTML" });
  });

  // ---- admin queue ----
  bot.command("queue", async (ctx, next) => {
    if (!ctx.isAdmin || !inDm(ctx)) return next();
    const rows = await openQueue(ctx.env);
    if (rows.length === 0) return say(ctx, "Queue is empty.");
    const lines = rows.map((r) => `#${r.id} <b>${esc(r.name)}</b> — ${esc(r.username ? "@" + r.username : r.first_name ?? String(r.user_id))} · ${r.created_at.slice(0, 10)}\n   /fulfill ${r.id} [note] · /refundorder ${r.id}`);
    await say(ctx, `🧾 <b>Open orders</b>\n${lines.join("\n")}`);
  });

  bot.command("fulfill", async (ctx, next) => {
    if (!ctx.isAdmin || !inDm(ctx) || !ctx.from) return next();
    const [idS, ...note] = (ctx.match?.toString() ?? "").trim().split(/\s+/);
    const id = Number(idS);
    if (!id) return say(ctx, "Usage: /fulfill &lt;id&gt; [note]");
    await say(ctx, esc(await fulfillOrder(ctx.env, ctx.api, ctx.from.id, id, note.join(" ") || undefined)));
  });

  bot.command("refundorder", async (ctx, next) => {
    if (!ctx.isAdmin || !inDm(ctx) || !ctx.from) return next();
    const id = Number((ctx.match?.toString() ?? "").trim().split(/\s+/)[0]);
    if (!id) return say(ctx, "Usage: /refundorder &lt;id&gt;");
    await say(ctx, esc(await refundOrder(ctx.env, ctx.api, ctx.from.id, id)));
  });
}
