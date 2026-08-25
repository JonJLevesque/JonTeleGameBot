/** CSV export of members + memberships + points. */
import type { Env } from "../../env";

function cell(v: unknown): string {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export async function exportCsv(env: Env): Promise<string> {
  const rows = await env.DB.prepare(
    `SELECT m.user_id, m.username, m.first_name, m.joined_at, m.last_seen_at, m.referrer_id,
            ms.state, ms.rail, ms.tier, ms.period_end_at, ms.grace_until,
            COALESCE(pb.balance, 0) AS points, COALESCE(xt.xp, 0) AS xp, COALESCE(xt.level, 0) AS level,
            COALESCE(st.current, 0) AS streak
       FROM members m
       LEFT JOIN memberships ms ON ms.user_id = m.user_id
       LEFT JOIN points_balances pb ON pb.user_id = m.user_id
       LEFT JOIN xp_totals xt ON xt.user_id = m.user_id
       LEFT JOIN streaks st ON st.user_id = m.user_id
       ORDER BY m.joined_at`,
  ).all<Record<string, unknown>>();
  const cols = ["user_id", "username", "first_name", "joined_at", "last_seen_at", "referrer_id", "state", "rail", "tier", "period_end_at", "grace_until", "points", "xp", "level", "streak"];
  const lines = [cols.join(",")];
  for (const r of rows.results) lines.push(cols.map((c) => cell(r[c])).join(","));
  return lines.join("\n") + "\n";
}
