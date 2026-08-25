/** /slots: stake → 🎰 dice → payout. Stake is deducted before the roll; a failed send refunds. */
import type { Api } from "grammy";
import type { Config } from "../../config";
import type { Env } from "../../env";
import { bumpCounter } from "../../db";
import { reels, slotsMultiplier, slotsPayout } from "../../domain/slots";
import { applyPoints, getPoints, getXp, InsufficientPoints } from "../../services/ledger";
import { fmtPoints } from "./common";

const REEL_ICONS = ["🍫", "🍒", "🍋", "7️⃣"] as const;

export type SpinResult =
  | { ok: true; value: number; stake: number; win: number; multiplier: number; balance: number; reels: string }
  | { ok: false; reason: "bad_stake" | "level" | "cooldown" | "daily_cap" | "insufficient" | "send_failed"; detail?: string };

export function parseStake(cfg: Config, arg: string | undefined): number | null {
  const n = Number.parseInt(arg ?? "", 10);
  if (!Number.isFinite(n) || n < cfg.economy.slotsMin || n > cfg.economy.slotsMax) return null;
  return n;
}

export function reelText(value: number): string {
  return reels(value).map((r) => REEL_ICONS[r]).join(" ");
}

/** `ref` must be unique per spin attempt (the Telegram update id). */
export async function spin(env: Env, cfg: Config, api: Api, p: { chatId: number; userId: number; day: string; stake: number; ref: string; threadId?: number }): Promise<SpinResult> {
  const e = cfg.economy;
  if (p.stake < e.slotsMin || p.stake > e.slotsMax) return { ok: false, reason: "bad_stake" };
  const { level } = await getXp(env, p.userId);
  if (level < e.slotsMinLevel) return { ok: false, reason: "level", detail: String(e.slotsMinLevel) };

  if (await slotsCooldownActive(env, p.userId)) return { ok: false, reason: "cooldown", detail: String(e.slotsCooldownSec) };
  const spins = await bumpCounter(env, p.userId, p.day, "spins", e.slotsDailyCap);
  if (spins === null) return { ok: false, reason: "daily_cap", detail: String(e.slotsDailyCap) };
  // KV's minimum TTL is 60s, so the value carries the real deadline.
  await env.KV.put(`slots:${p.userId}`, String(Date.now() + e.slotsCooldownSec * 1000), { expirationTtl: Math.max(60, e.slotsCooldownSec) }).catch(() => {});

  const stakeRef = `slots:${p.ref}`;
  try {
    await applyPoints(env, p.userId, -p.stake, "slots_stake", { ref: stakeRef });
  } catch (err) {
    if (err instanceof InsufficientPoints) return { ok: false, reason: "insufficient" };
    throw err;
  }

  let value: number;
  try {
    const msg = await api.sendDice(p.chatId, "🎰", { message_thread_id: p.threadId });
    value = msg.dice.value;
  } catch (err) {
    console.warn("sendDice failed", String(err));
    await applyPoints(env, p.userId, p.stake, "slots_refund", { ref: stakeRef }).catch(() => {});
    return { ok: false, reason: "send_failed" };
  }

  const win = slotsPayout(p.stake, value);
  const balance = win > 0
    ? (await applyPoints(env, p.userId, win, "slots_win", { ref: `slots_win:${p.ref}` })).balance
    : await getPoints(env, p.userId);
  return { ok: true, value, stake: p.stake, win, multiplier: slotsMultiplier(value), balance, reels: reelText(value) };
}

/** True while the per-user cooldown deadline stored in KV is in the future. */
export async function slotsCooldownActive(env: Env, userId: number): Promise<boolean> {
  const v = await env.KV.get(`slots:${userId}`).catch(() => null);
  if (!v) return false;
  const deadline = Number(v);
  return !Number.isFinite(deadline) || Date.now() < deadline;
}

export function spinText(cfg: Config, r: Extract<SpinResult, { ok: true }>): string {
  const head = `🎰 ${r.reels}`;
  if (r.win === 0) return `${head}\nNo luck. -${fmtPoints(cfg, r.stake)}. Balance: ${r.balance}.`;
  const net = r.win - r.stake;
  const tag = r.multiplier >= 10 ? "JACKPOT ×10!" : r.multiplier >= 5 ? "Triple! ×5" : r.multiplier > 1 ? "Pair ×1.5" : "Stake back";
  return `${head}\n${tag} +${fmtPoints(cfg, r.win)} (net ${net >= 0 ? "+" : ""}${net}). Balance: ${r.balance}.`;
}

export function spinErrorText(cfg: Config, r: Extract<SpinResult, { ok: false }>): string {
  const e = cfg.economy;
  switch (r.reason) {
    case "bad_stake": return `Stake must be between ${e.slotsMin} and ${e.slotsMax} ${cfg.pointsName}. Example: /slots ${e.slotsMin}`;
    case "level": return `Slots unlock at level ${e.slotsMinLevel}.`;
    case "cooldown": return `Easy — one spin every ${e.slotsCooldownSec}s.`;
    case "daily_cap": return `You've hit today's ${e.slotsDailyCap} spins. Back tomorrow.`;
    case "insufficient": return `Not enough ${cfg.pointsName} for that stake.`;
    case "send_failed": return "Couldn't roll the reels; your stake was refunded.";
  }
}
