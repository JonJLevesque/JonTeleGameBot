import type { Env } from "../env";

const TABLES = ["members", "attestations", "memberships", "membership_transitions", "payments", "xp_events", "xp_totals",
  "points_ledger", "points_balances", "awards", "member_awards", "streaks", "drops", "trivia_bank", "trivia_rounds",
  "shop_items", "purchases", "tips", "reports", "audit_log", "config"];

/** Nightly JSONL dump of every table to R2 (D1 Time Travel is the primary restore path). */
export async function backupToR2(env: Env) {
  const day = new Date().toISOString().slice(0, 10);
  for (const t of TABLES) {
    const rows = await env.DB.prepare(`SELECT * FROM ${t}`).all();
    const body = rows.results.map((r) => JSON.stringify(r)).join("\n");
    await env.BACKUPS.put(`backups/${day}/${t}.jsonl`, body);
  }
}
