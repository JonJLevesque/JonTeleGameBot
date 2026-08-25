/** Window stats used by /stats and the weekly report. */
import type { Env } from "../../env";

export interface Stats {
  days: number;
  since: string;
  members: { active: number; grace: number; lapsed: number; newMembers: number; quiet: number };
  revenue: Array<{ rail: string; tier: string | null; currency: string; amount: number; count: number }>;
  messages: number;
  points: { issued: number; sunk: number };
  topXp: Array<{ user_id: number; first_name: string; xp: number }>;
  openPurchases: number;
}

export const QUIET_DAYS = 5;

export async function computeStats(env: Env, days: number): Promise<Stats> {
  const since = new Date(Date.now() - days * 86400000).toISOString();
  const quietCutoff = new Date(Date.now() - QUIET_DAYS * 86400000).toISOString();
  const [states, newMembers, quiet, revenue, messages, points, topXp, open] = await Promise.all([
    env.DB.prepare("SELECT state, COUNT(*) AS n FROM memberships GROUP BY state").all<{ state: string; n: number }>(),
    env.DB.prepare("SELECT COUNT(*) AS n FROM members WHERE joined_at >= ?").bind(since).first<{ n: number }>(),
    env.DB.prepare("SELECT COUNT(*) AS n FROM memberships ms JOIN members m ON m.user_id = ms.user_id WHERE ms.state = 'active' AND m.last_seen_at < ?").bind(quietCutoff).first<{ n: number }>(),
    env.DB.prepare("SELECT rail, tier, currency, SUM(amount) AS amount, COUNT(*) AS count FROM payments WHERE occurred_at >= ? AND kind NOT IN ('refund','chargeback') GROUP BY rail, tier, currency ORDER BY rail, tier").bind(since)
      .all<{ rail: string; tier: string | null; currency: string; amount: number; count: number }>(),
    env.DB.prepare("SELECT COUNT(*) AS n FROM xp_events WHERE reason = 'msg' AND at >= ?").bind(since).first<{ n: number }>(),
    env.DB.prepare("SELECT COALESCE(SUM(CASE WHEN delta > 0 THEN delta END), 0) AS issued, COALESCE(-SUM(CASE WHEN delta < 0 THEN delta END), 0) AS sunk FROM points_ledger WHERE at >= ?").bind(since).first<{ issued: number; sunk: number }>(),
    env.DB.prepare("SELECT x.user_id, m.first_name, SUM(x.delta) AS xp FROM xp_events x JOIN members m ON m.user_id = x.user_id WHERE x.at >= ? GROUP BY x.user_id ORDER BY xp DESC LIMIT 5").bind(since)
      .all<{ user_id: number; first_name: string; xp: number }>(),
    env.DB.prepare("SELECT COUNT(*) AS n FROM purchases WHERE status = 'queued'").first<{ n: number }>(),
  ]);
  const byState = Object.fromEntries(states.results.map((r) => [r.state, r.n]));
  return {
    days, since,
    members: { active: byState.active ?? 0, grace: byState.grace ?? 0, lapsed: byState.lapsed ?? 0, newMembers: newMembers?.n ?? 0, quiet: quiet?.n ?? 0 },
    revenue: revenue.results,
    messages: messages?.n ?? 0,
    points: { issued: points?.issued ?? 0, sunk: points?.sunk ?? 0 },
    topXp: topXp.results,
    openPurchases: open?.n ?? 0,
  };
}

/** Plain-text table (monospace-friendly, no HTML). */
export function formatStats(s: Stats, title = `Last ${s.days} days`): string {
  const rows: string[] = [title, ""];
  const pad = (a: string, b: string | number) => `${a.padEnd(16)}${String(b)}`;
  rows.push(pad("Active", s.members.active), pad("Grace", s.members.grace), pad("Lapsed", s.members.lapsed),
    pad("New members", s.members.newMembers), pad("Quiet (>5d)", s.members.quiet), pad("Messages (xp)", s.messages),
    pad("Points issued", s.points.issued), pad("Points sunk", s.points.sunk), pad("Open purchases", s.openPurchases), "");
  rows.push("Revenue:");
  if (!s.revenue.length) rows.push("  none");
  for (const r of s.revenue) rows.push(`  ${r.rail}/${r.tier ?? "-"}: ${r.amount} ${r.currency} (${r.count})`);
  rows.push("", "Top XP:");
  if (!s.topXp.length) rows.push("  none");
  s.topXp.forEach((t, i) => rows.push(`  ${i + 1}. ${t.first_name} +${t.xp}`));
  return rows.join("\n");
}
