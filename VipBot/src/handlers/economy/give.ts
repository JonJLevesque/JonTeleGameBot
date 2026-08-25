/** /give @user N — peer-to-peer points transfer with anti-abuse rules. */
import type { Bot } from "grammy";
import type { Ctx } from "../../context";
import type { Env } from "../../env";
import type { Config } from "../../config";
import { getCounter, type MemberRow } from "../../db";
import { applyPoints, getXp, InsufficientPoints } from "../../services/ledger";
import { esc, mention } from "../../services/telegram";
import { argsOf, displayName, inGroup, quietReply, resolveTarget } from "./common";

export const givePairKey = (from: number, to: number) => `give:${from}:${to}`;
export const gaveKey = (to: number, from: number) => `gave:${to}:${from}`;

export type GiveResult = { ok: true; fromBalance: number } | { ok: false; reason: string };

export async function doGive(env: Env, cfg: Config, giver: MemberRow, to: MemberRow, amount: number, updateId: number): Promise<GiveResult> {
  const e = cfg.economy;
  if (!Number.isInteger(amount) || amount <= 0) return { ok: false, reason: "Amount must be a whole number above 0." };
  if (giver.user_id === to.user_id) return { ok: false, reason: "You can't give to yourself." };
  const { level } = await getXp(env, giver.user_id);
  if (level < e.giveMinLevel) return { ok: false, reason: `Giving unlocks at Level ${e.giveMinLevel}.` };
  const ageDays = (Date.now() - Date.parse(giver.joined_at)) / 86400000;
  if (ageDays < e.giveMinAgeDays) return { ok: false, reason: `Giving unlocks after ${e.giveMinAgeDays} days of membership.` };
  if (await env.KV.get(givePairKey(giver.user_id, to.user_id))) return { ok: false, reason: `You gave to them recently — wait ${e.givePairCooldownMin} min.` };
  if (await env.KV.get(gaveKey(giver.user_id, to.user_id))) return { ok: false, reason: "They gave to you in the last 24h — no gifting back yet." };
  const day = new Date().toISOString().slice(0, 10);
  const used = await getCounter(env, giver.user_id, day, "give_out");
  if (used + amount > e.giveDailyCap) return { ok: false, reason: `Daily give cap is ${e.giveDailyCap}; you have ${Math.max(0, e.giveDailyCap - used)} left.` };
  const ref = `give:${updateId}`;
  let fromBalance: number;
  try {
    fromBalance = (await applyPoints(env, giver.user_id, -amount, "give_out", { ref, actorId: giver.user_id })).balance;
  } catch (err) {
    if (err instanceof InsufficientPoints) return { ok: false, reason: "Not enough points." };
    throw err;
  }
  try {
    await applyPoints(env, to.user_id, amount, "give_in", { ref, actorId: giver.user_id });
  } catch (err) {
    await applyPoints(env, giver.user_id, amount, "give_refund", { ref, actorId: giver.user_id });
    return { ok: false, reason: "Transfer failed; refunded." };
  }
  // Count units, not calls: bump the counter `amount` times is wasteful; store directly.
  await env.DB.prepare(
    `INSERT INTO activity_counters (user_id, day, key, count, last_at) VALUES (?, ?, 'give_out', ?, ?)
     ON CONFLICT (user_id, day, key) DO UPDATE SET count = count + excluded.count, last_at = excluded.last_at`,
  ).bind(giver.user_id, day, amount, new Date().toISOString()).run();
  await env.KV.put(givePairKey(giver.user_id, to.user_id), "1", { expirationTtl: Math.max(60, e.givePairCooldownMin * 60) });
  await env.KV.put(gaveKey(to.user_id, giver.user_id), "1", { expirationTtl: 24 * 3600 });
  return { ok: true, fromBalance };
}

export function registerGive(bot: Bot<Ctx>) {
  bot.command("give", async (ctx) => {
    if (!ctx.from || !inGroup(ctx)) return;
    const t = await resolveTarget(ctx, argsOf(ctx));
    if (!t) { await quietReply(ctx, "Usage: /give @user N (or reply to their message)."); return; }
    const amount = Number(t.rest[0]);
    const giver = await ctx.env.DB.prepare("SELECT * FROM members WHERE user_id = ?").bind(ctx.from.id).first<MemberRow>();
    if (!giver) return;
    const r = await doGive(ctx.env, ctx.cfg, giver, t.member, amount, ctx.update.update_id);
    if (!r.ok) { await quietReply(ctx, r.reason); return; }
    const cfg = ctx.cfg;
    await ctx.reply(`${cfg.pointsEmoji} ${mention(ctx.from.id, ctx.from.first_name)} gave <b>${amount} ${cfg.pointsName}</b> to ${mention(t.member.user_id, esc(displayName(t.member)))}.`, { parse_mode: "HTML" });
  });
}
