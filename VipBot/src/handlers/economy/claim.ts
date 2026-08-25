/** /claim — daily streak claim. */
import type { Bot } from "grammy";
import type { Ctx } from "../../context";
import type { Env } from "../../env";
import type { Config } from "../../config";
import { applyClaim, type ClaimResult, type ClaimRules, type StreakState } from "../../domain/streaks";
import { applyPoints, applyXp } from "../../services/ledger";
import { quietReply } from "./common";
import { announceLevelUp } from "./xp";

export function claimRules(cfg: Config): ClaimRules {
  const e = cfg.economy;
  return { base: e.claimBase, bonusCap: e.claimBonusCap, multiplier: e.claimMultiplier, xp: e.claimXp,
    milestoneDays: e.streakMilestoneDays, milestonePoints: e.streakMilestonePoints, milestoneXp: e.streakMilestoneXp };
}

export async function getStreak(env: Env, userId: number): Promise<StreakState> {
  const r = await env.DB.prepare("SELECT current, best, last_claim_date, savers FROM streaks WHERE user_id = ?").bind(userId)
    .first<{ current: number; best: number; last_claim_date: string | null; savers: number }>();
  return r ? { current: r.current, best: r.best, lastClaimDate: r.last_claim_date, savers: r.savers } : { current: 0, best: 0, lastClaimDate: null, savers: 0 };
}

export async function saveStreak(env: Env, userId: number, s: StreakState) {
  await env.DB.prepare(
    `INSERT INTO streaks (user_id, current, best, last_claim_date, savers) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT (user_id) DO UPDATE SET current = excluded.current, best = excluded.best, last_claim_date = excluded.last_claim_date, savers = excluded.savers`,
  ).bind(userId, s.current, s.best, s.lastClaimDate, s.savers).run();
}

export interface ClaimOutcome extends ClaimResult { first: boolean; leveledUpTo: number | null }

/** Applies a claim for `day`; first-ever claim is doubled. Idempotent per (uid, day). */
export async function doClaim(env: Env, cfg: Config, userId: number, day: string): Promise<ClaimOutcome> {
  const prev = await getStreak(env, userId);
  const res = applyClaim(prev, day, claimRules(cfg));
  if (!res.ok) return { ...res, first: false, leveledUpTo: null };
  const first = prev.lastClaimDate === null && prev.current === 0;
  const points = first ? res.points * 2 : res.points;
  const xp = first ? res.xp * 2 : res.xp;
  await saveStreak(env, userId, res.state);
  const ref = `claim:${userId}:${day}`;
  await applyPoints(env, userId, points, "claim", { ref });
  const x = await applyXp(env, userId, xp, "claim", ref);
  return { ...res, points, xp, first, leveledUpTo: x.leveledUpTo };
}

export function registerClaim(bot: Bot<Ctx>) {
  bot.command("claim", async (ctx) => {
    if (!ctx.from) return;
    const cfg = ctx.cfg;
    const r = await doClaim(ctx.env, cfg, ctx.from.id, ctx.day);
    if (!r.ok) {
      await quietReply(ctx, `You already claimed today. Streak: <b>${r.streak}</b> 🔥 — come back tomorrow.`);
      return;
    }
    const lines = [
      `${cfg.pointsEmoji} <b>+${r.points} ${cfg.pointsName}</b> · ${cfg.xpEmoji} +${r.xp} ${cfg.xpName}`,
      `Streak: <b>${r.streak} day${r.streak === 1 ? "" : "s"}</b>`,
    ];
    if (r.first) lines.push("✨ First claim — doubled.");
    if (r.usedSaver) lines.push(`🛟 A streak saver kept you alive (${r.state.savers} left).`);
    if (r.milestone) lines.push(`🏁 Milestone! ${cfg.economy.streakMilestoneDays}-day bonus included.`);
    await quietReply(ctx, lines.join("\n"));
    await announceLevelUp(ctx, ctx.from.id, ctx.from.first_name, r.leveledUpTo);
  });
}
