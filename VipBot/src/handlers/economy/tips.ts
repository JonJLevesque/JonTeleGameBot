/** Stars tips through the bot: /tip <stars> (DM) → invoice → successful_payment → XP + points. */
import type { Bot } from "grammy";
import type { Ctx } from "../../context";
import type { Env } from "../../env";
import type { Config } from "../../config";
import { nowIso } from "../../db";
import { applyPoints, applyXp } from "../../services/ledger";
import { argsOf, isPrivate } from "./common";
import { announceLevelUp } from "./xp";

export const TIP_PAYLOAD = "tip:";

export interface TipOutcome { recorded: boolean; xp: number; points: number; leveledUpTo: number | null }

/** Idempotent on charge_id. XP capped daily via `tip_xp` (units = stars). */
export async function recordTip(env: Env, cfg: Config, userId: number, stars: number, chargeId: string, day: string): Promise<TipOutcome> {
  const ins = await env.DB.prepare("INSERT OR IGNORE INTO tips (user_id, stars, charge_id, at) VALUES (?, ?, ?, ?)")
    .bind(userId, stars, chargeId, nowIso()).run();
  if ((ins.meta.changes ?? 0) === 0) return { recorded: false, xp: 0, points: 0, leveledUpTo: null };
  // Mirror into payments so revenue stats include tips and admin /refund can find the charge id.
  await env.DB.prepare("INSERT OR IGNORE INTO payments (user_id, rail, external_event_id, external_txn_id, kind, amount, currency, occurred_at) VALUES (?, 'stars', ?, ?, 'stars_tip', ?, 'XTR', ?)")
    .bind(userId, `tip:${chargeId}`, chargeId, stars, nowIso()).run();
  const e = cfg.economy;
  // Daily XP cap: reserve `stars` units against the cap in one atomic update.
  const wanted = stars * e.tipXpPerStar;
  const t = nowIso();
  await env.DB.prepare("INSERT OR IGNORE INTO activity_counters (user_id, day, key, count, last_at) VALUES (?, ?, 'tip_xp', 0, ?)").bind(userId, day, t).run();
  const before = await env.DB.prepare("SELECT count FROM activity_counters WHERE user_id = ? AND day = ? AND key = 'tip_xp'").bind(userId, day).first<{ count: number }>();
  const room = Math.max(0, e.tipXpDailyCap - (before?.count ?? 0));
  const xp = Math.min(wanted, room);
  if (xp > 0) {
    await env.DB.prepare("UPDATE activity_counters SET count = count + ?, last_at = ? WHERE user_id = ? AND day = ? AND key = 'tip_xp'").bind(xp, t, userId, day).run();
  }
  const ref = `tip:${chargeId}`;
  const points = e.tipPointsPerStars > 0 ? Math.floor(stars / e.tipPointsPerStars) : 0;
  const x = xp > 0 ? await applyXp(env, userId, xp, "tip", ref) : null;
  if (points > 0) await applyPoints(env, userId, points, "tip", { ref });
  return { recorded: true, xp, points, leveledUpTo: x?.leveledUpTo ?? null };
}

export function registerTips(bot: Bot<Ctx>) {
  bot.command("tip", async (ctx) => {
    if (!ctx.from || !isPrivate(ctx)) return;
    const stars = Number(argsOf(ctx)[0]);
    if (!Number.isInteger(stars) || stars < 1 || stars > 10000) { await ctx.reply("Usage: /tip <stars> (1–10000)"); return; }
    await ctx.api.sendInvoice(ctx.chat.id, `Tip ${ctx.cfg.creatorName}`, `A ${stars}⭐ tip for ${ctx.cfg.creatorName}. Thank you!`,
      `${TIP_PAYLOAD}${ctx.from.id}:${Date.now()}`, "XTR", [{ label: "Tip", amount: stars }], { provider_token: "" });
  });

  bot.on("pre_checkout_query", async (ctx, next) => {
    await ctx.answerPreCheckoutQuery(true).catch((e) => console.warn("pre_checkout answer failed", String(e)));
    await next();
  });

  bot.on("message:successful_payment", async (ctx, next) => {
    const sp = ctx.msg.successful_payment;
    if (sp.currency === "XTR" && sp.invoice_payload.startsWith(TIP_PAYLOAD) && ctx.from) {
      const r = await recordTip(ctx.env, ctx.cfg, ctx.from.id, sp.total_amount, sp.telegram_payment_charge_id, ctx.day);
      if (r.recorded) {
        const cfg = ctx.cfg;
        await ctx.reply(`💖 Thank you for the ${sp.total_amount}⭐ tip! +${r.xp} ${cfg.xpName}${r.points ? ` · +${r.points} ${cfg.pointsName}` : ""}.`);
        await announceLevelUp(ctx, ctx.from.id, ctx.from.first_name, r.leveledUpTo);
      }
    }
    await next();
  });
}
