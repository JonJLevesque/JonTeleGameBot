import type { Config } from "../config";
import type { Env } from "../env";
import { localHour, localWeekday, localDay } from "../db";
import { Api } from "grammy";
import { postWeeklyReport } from "../handlers/admin/report";
import { expireTitles, refundStaleOrders } from "../handlers/shop";
import { startTriviaRound } from "../handlers/games/trivia";
import { postLobbyDigest, runLobbyTrivia } from "../handlers/lobby";

export async function hourlySweep(env: Env, cfg: Config) {
  const api = new Api(env.TG_BOT_TOKEN);
  await refundStaleOrders(env, api).catch((e) => console.error("refundStaleOrders", String(e)));
  await expireTitles(env, cfg, api).catch((e) => console.error("expireTitles", String(e)));
  await scheduledTrivia(env, cfg, api).catch((e) => console.error("scheduledTrivia", String(e)));
  await scheduledLobbyTrivia(env, cfg, api).catch((e) => console.error("scheduledLobbyTrivia", String(e)));
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
  const posted = await postWeeklyReport(env, ctx, cfg, weekKey);
  if (posted !== false && cfg.lobbyChatId) {
    const api = new Api(env.TG_BOT_TOKEN);
    const me = await api.getMe();
    await postLobbyDigest(env, cfg, api, me.username).catch((e) => console.error("lobby digest", String(e)));
  }
}

/** Daily trivia at 20:00 creator time, once per day (KV guard). */
async function scheduledTrivia(env: Env, cfg: Config, api: Api) {
  if (!cfg.groupChatId || localHour(cfg.creatorTz) !== 20) return;
  const key = `trivia_daily:${localDay(cfg.creatorTz)}`;
  if (await env.KV.get(key)) return;
  await env.KV.put(key, "1", { expirationTtl: 86400 });
  await startTriviaRound(env, cfg, api, cfg.groupChatId, { threadId: cfg.gamesTopicId ?? undefined });
}

/** Win-a-pass trivia in the Lobby at 19:00 creator time, once per day. */
async function scheduledLobbyTrivia(env: Env, cfg: Config, api: Api) {
  if (!cfg.lobbyChatId || localHour(cfg.creatorTz) !== 19) return;
  const key = `lobby_trivia_daily:${localDay(cfg.creatorTz)}`;
  if (await env.KV.get(key)) return;
  await env.KV.put(key, "1", { expirationTtl: 86400 });
  await runLobbyTrivia(env, cfg, api);
}
