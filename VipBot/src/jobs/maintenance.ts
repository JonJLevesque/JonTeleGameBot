import type { Config } from "../config";
import type { Env } from "../env";
import { localHour, localWeekday, localDay } from "../db";
import { postWeeklyReport } from "../handlers/admin/report";

export async function hourlySweep(env: Env, _cfg: Config) {
  const cutoff = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  await env.DB.prepare("DELETE FROM update_dedupe WHERE received_at < ?").bind(cutoff).run();
  await env.DB.prepare("DELETE FROM activity_counters WHERE day < ?").bind(new Date(Date.now() - 3 * 86400000).toISOString().slice(0, 10)).run();
  await env.DB.prepare("DELETE FROM drops WHERE claimed_by IS NULL AND expires_at < ?").bind(cutoff).run();
}

/** Daily-cron-with-guard: Monday 09:00 creator tz, once per ISO week (keyed row), self-heals after downtime. */
export async function weeklyReportGuard(env: Env, ctx: ExecutionContext, cfg: Config) {
  const now = new Date();
  if (localWeekday(cfg.creatorTz, now) !== 1 || localHour(cfg.creatorTz, now) < 9) return;
  const weekKey = localDay(cfg.creatorTz, now); // the Monday date
  const exists = await env.DB.prepare("SELECT 1 FROM reports WHERE week_key = ?").bind(weekKey).first();
  if (exists) return;
  await postWeeklyReport(env, ctx, cfg, weekKey);
}
