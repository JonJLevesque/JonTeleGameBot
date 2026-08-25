/** Thin typed D1 helpers. Keep SQL here or next to its feature; no ORM. */
import type { Env } from "../env";

export const nowIso = () => new Date().toISOString();

/** YYYY-MM-DD for `date` in an IANA tz. Creator-tz day boundaries for streaks/caps. */
export function localDay(tz: string, date: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export function localHour(tz: string, date: Date = new Date()): number {
  return Number(new Intl.DateTimeFormat("en-US", { timeZone: tz, hour: "numeric", hour12: false }).format(date)) % 24;
}

export function localWeekday(tz: string, date: Date = new Date()): number {
  // 0 = Sunday … 6 = Saturday
  const s = new Intl.DateTimeFormat("en-US", { timeZone: tz, weekday: "short" }).format(date);
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(s);
}

/** True if this update_id has NOT been seen before (and records it). */
export async function dedupeUpdate(env: Env, updateId: number): Promise<boolean> {
  const r = await env.DB.prepare("INSERT OR IGNORE INTO update_dedupe (update_id, received_at) VALUES (?, ?)")
    .bind(updateId, nowIso()).run();
  return (r.meta.changes ?? 0) > 0;
}

export async function upsertMember(env: Env, u: { id: number; username?: string; first_name: string }, referrerId?: number) {
  const t = nowIso();
  await env.DB.prepare(
    `INSERT INTO members (user_id, username, first_name, joined_at, last_seen_at, referrer_id)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT (user_id) DO UPDATE SET username = excluded.username, first_name = excluded.first_name, last_seen_at = excluded.last_seen_at`,
  ).bind(u.id, u.username?.toLowerCase() ?? null, u.first_name, t, t, referrerId ?? null).run();
}

export interface MemberRow { user_id: number; username: string | null; first_name: string; joined_at: string; last_seen_at: string; referrer_id: number | null }
export async function getMember(env: Env, userId: number) {
  return env.DB.prepare("SELECT * FROM members WHERE user_id = ?").bind(userId).first<MemberRow>();
}
export async function findMemberByUsername(env: Env, username: string) {
  return env.DB.prepare("SELECT * FROM members WHERE username = ?").bind(username.replace(/^@/, "").toLowerCase()).first<MemberRow>();
}

export async function audit(env: Env, actorId: number | null, action: string, target?: string | number, payload?: unknown) {
  await env.DB.prepare("INSERT INTO audit_log (actor_id, action, target, payload_json, at) VALUES (?, ?, ?, ?, ?)")
    .bind(actorId, action, target == null ? null : String(target), payload == null ? null : JSON.stringify(payload), nowIso()).run();
}

/** Atomic per-user daily counter with cap. Returns the new count, or null if the cap was hit (no increment). */
export async function bumpCounter(env: Env, userId: number, day: string, key: string, cap: number, cooldownSec = 0): Promise<number | null> {
  const t = nowIso();
  const cutoff = new Date(Date.now() - cooldownSec * 1000).toISOString();
  const r = await env.DB.prepare(
    `INSERT INTO activity_counters (user_id, day, key, count, last_at) VALUES (?, ?, ?, 1, ?)
     ON CONFLICT (user_id, day, key) DO UPDATE SET count = count + 1, last_at = excluded.last_at
     WHERE count < ? AND (last_at IS NULL OR last_at <= ?)`,
  ).bind(userId, day, key, t, cap, cutoff).run();
  if ((r.meta.changes ?? 0) === 0) return null;
  const row = await env.DB.prepare("SELECT count FROM activity_counters WHERE user_id = ? AND day = ? AND key = ?").bind(userId, day, key).first<{ count: number }>();
  return row?.count ?? null;
}

export async function getCounter(env: Env, userId: number, day: string, key: string): Promise<number> {
  const row = await env.DB.prepare("SELECT count FROM activity_counters WHERE user_id = ? AND day = ? AND key = ?").bind(userId, day, key).first<{ count: number }>();
  return row?.count ?? 0;
}
