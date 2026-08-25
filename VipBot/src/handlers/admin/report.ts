/** Weekly creator report: guard row first, DM admins, optionally enqueue an AI briefing. */
import { Api } from "grammy";
import type { Config } from "../../config";
import type { Env } from "../../env";
import { nowIso } from "../../db";
import { aiEnabled } from "../../services/ai";
import { computeStats, formatStats, type Stats } from "./stats";

export async function buildWeeklyStats(env: Env): Promise<Stats> {
  return computeStats(env, 7);
}

export async function postWeeklyReport(env: Env, _ctx: ExecutionContext, cfg: Config, weekKey: string, api: Api = new Api(env.TG_BOT_TOKEN)) {
  const stats = await buildWeeklyStats(env);
  const statsJson = JSON.stringify(stats);
  const ins = await env.DB.prepare("INSERT OR IGNORE INTO reports (week_key, posted_at, stats_json) VALUES (?, ?, ?)")
    .bind(weekKey, nowIso(), statsJson).run();
  if ((ins.meta.changes ?? 0) === 0) return false; // already posted this week
  const text = formatStats(stats, `${cfg.communityName} — week of ${weekKey}`);
  for (const id of env.ADMIN_USER_IDS.split(",").map((s) => Number(s.trim())).filter(Boolean)) {
    await api.sendMessage(id, text).catch((e) => console.warn("report dm failed", id, String(e)));
  }
  if (aiEnabled(env, cfg)) await env.AI_JOBS.send({ kind: "weekly_summary", weekKey, statsJson });
  return true;
}
