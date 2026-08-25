import { env } from "cloudflare:test";
import { DEFAULT_CONFIG, type Config } from "../src/config";
import { nowIso } from "../src/db";

export const testCfg = (patch: Partial<Config> = {}): Config => ({ ...structuredClone(DEFAULT_CONFIG), groupChatId: -1001, ...patch });

export async function seedMember(userId: number, opts: { state?: string; tier?: string | null; balance?: number; xp?: number; level?: number; name?: string } = {}) {
  const t = nowIso();
  await env.DB.prepare("INSERT OR REPLACE INTO members (user_id, username, first_name, joined_at, last_seen_at) VALUES (?, ?, ?, ?, ?)")
    .bind(userId, `u${userId}`, opts.name ?? `User${userId}`, t, t).run();
  await env.DB.prepare("INSERT OR REPLACE INTO memberships (user_id, state, tier, last_transition_at) VALUES (?, ?, ?, ?)")
    .bind(userId, opts.state ?? "active", opts.tier ?? "vip", t).run();
  await env.DB.prepare("INSERT OR REPLACE INTO points_balances (user_id, balance) VALUES (?, ?)").bind(userId, opts.balance ?? 0).run();
  if (opts.xp != null || opts.level != null)
    await env.DB.prepare("INSERT OR REPLACE INTO xp_totals (user_id, xp, level, announced_level) VALUES (?, ?, ?, 0)").bind(userId, opts.xp ?? 0, opts.level ?? 0).run();
}

export async function balance(userId: number): Promise<number> {
  const r = await env.DB.prepare("SELECT balance FROM points_balances WHERE user_id = ?").bind(userId).first<{ balance: number }>();
  return r?.balance ?? 0;
}
