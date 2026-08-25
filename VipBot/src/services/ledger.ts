/** The only way points and XP move. Every delta is logged with a reason and an
 *  idempotency ref; balances never go negative; XP feeds levels. */
import type { Env } from "../env";
import { nowIso } from "../db";
import { levelForXp } from "../domain/levels";

export class InsufficientPoints extends Error {}

export interface PointsResult { applied: boolean; balance: number }

/**
 * Apply a points delta. `ref` makes the call idempotent (same reason+ref → no-op).
 * Negative deltas that would overdraw are rejected with InsufficientPoints unless `clampToZero`.
 */
export async function applyPoints(
  env: Env, userId: number, delta: number, reason: string,
  opts: { ref?: string; actorId?: number; clampToZero?: boolean } = {},
): Promise<PointsResult> {
  const { DB } = env;
  await DB.prepare("INSERT OR IGNORE INTO points_balances (user_id, balance) VALUES (?, 0)").bind(userId).run();
  if (opts.ref) {
    const dup = await DB.prepare("SELECT 1 FROM points_ledger WHERE reason = ? AND ref_id = ?").bind(reason, opts.ref).first();
    if (dup) return { applied: false, balance: await getPoints(env, userId) };
  }
  let d = delta;
  if (d < 0 && opts.clampToZero) {
    const bal = await getPoints(env, userId);
    d = -Math.min(bal, -d);
  }
  const upd = await DB.prepare("UPDATE points_balances SET balance = balance + ? WHERE user_id = ? AND balance + ? >= 0")
    .bind(d, userId, d).run();
  if ((upd.meta.changes ?? 0) === 0) throw new InsufficientPoints(`user ${userId} cannot afford ${-d}`);
  const balance = await getPoints(env, userId);
  await DB.prepare("INSERT OR IGNORE INTO points_ledger (user_id, delta, balance_after, reason, ref_id, actor_id, at) VALUES (?, ?, ?, ?, ?, ?, ?)")
    .bind(userId, d, balance, reason, opts.ref ?? null, opts.actorId ?? null, nowIso()).run();
  return { applied: true, balance };
}

export async function getPoints(env: Env, userId: number): Promise<number> {
  const r = await env.DB.prepare("SELECT balance FROM points_balances WHERE user_id = ?").bind(userId).first<{ balance: number }>();
  return r?.balance ?? 0;
}

export interface XpResult { applied: boolean; xp: number; level: number; leveledUpTo: number | null }

/** Add XP (never negative). Returns the new level and, if a level boundary was crossed
 *  that hasn't been announced yet, `leveledUpTo` — the caller announces, exactly once. */
export async function applyXp(env: Env, userId: number, delta: number, reason: string, ref?: string): Promise<XpResult> {
  const { DB } = env;
  if (delta <= 0) { const s = await getXp(env, userId); return { applied: false, ...s, leveledUpTo: null }; }
  const ins = await DB.prepare("INSERT OR IGNORE INTO xp_events (user_id, delta, reason, ref_id, at) VALUES (?, ?, ?, ?, ?)")
    .bind(userId, delta, reason, ref ?? null, nowIso()).run();
  if ((ins.meta.changes ?? 0) === 0) { const s = await getXp(env, userId); return { applied: false, ...s, leveledUpTo: null }; }
  await DB.prepare("INSERT INTO xp_totals (user_id, xp, level) VALUES (?, ?, 0) ON CONFLICT (user_id) DO UPDATE SET xp = xp + excluded.xp")
    .bind(userId, delta).run();
  const { xp } = await getXp(env, userId);
  const level = levelForXp(xp);
  await DB.prepare("UPDATE xp_totals SET level = ? WHERE user_id = ?").bind(level, userId).run();
  // announce guard: atomic bump of announced_level
  const ann = await DB.prepare("UPDATE xp_totals SET announced_level = ? WHERE user_id = ? AND announced_level < ?")
    .bind(level, userId, level).run();
  return { applied: true, xp, level, leveledUpTo: (ann.meta.changes ?? 0) > 0 && level > 0 ? level : null };
}

export async function getXp(env: Env, userId: number): Promise<{ xp: number; level: number }> {
  const r = await env.DB.prepare("SELECT xp, level FROM xp_totals WHERE user_id = ?").bind(userId).first<{ xp: number; level: number }>();
  return r ?? { xp: 0, level: 0 };
}
