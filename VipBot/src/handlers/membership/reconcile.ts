/** Every 5 minutes: expire periods, expire grace, send grace reminders. For Stars members
 *  Telegram is the source of truth — at period end we ask whether they're still in the
 *  channel (renewed) before starting grace. */
import { Api } from "grammy";
import { tierByCode, type Config } from "../../config";
import { bumpCounter, nowIso } from "../../db";
import { memberStub } from "../../do/MemberDO";
import type { Env } from "../../env";
import { dm, esc } from "../../services/telegram";
import { runEffects } from "./effects";
import { recordStarsSubscription } from "./payments";

interface Row { user_id: number; rail: "stars" | "external" | null; tier: string | null; period_end_at: string | null; grace_until: string | null }
const BATCH = 200;
const STARS_PERIOD_MS = 30 * 86400_000;

export async function reconcileMemberships(env: Env, _ctx: ExecutionContext, cfg: Config, api: Api = new Api(env.TG_BOT_TOKEN)) {
  const now = nowIso();
  await endPeriods(env, api, cfg, now);
  await expireGrace(env, api, cfg, now);
  await graceReminders(env, api, cfg, now);
}

async function endPeriods(env: Env, api: Api, cfg: Config, now: string) {
  const rows = await env.DB.prepare("SELECT user_id, rail, tier, period_end_at, grace_until FROM memberships WHERE state = 'active' AND period_end_at IS NOT NULL AND period_end_at <= ? LIMIT ?")
    .bind(now, BATCH).all<Row>();
  for (const r of rows.results) {
    try {
      if (r.rail === "stars" && cfg.channelChatId && (await stillSubscribed(api, cfg.channelChatId, r.user_id))) {
        const tier = tierByCode(cfg, r.tier) ?? cfg.tiers[0];
        const base = Math.max(Date.parse(r.period_end_at!), Date.now() - STARS_PERIOD_MS);
        const res = await recordStarsSubscription(env, r.user_id, tier?.code ?? "vip", tier?.stars ?? 0, new Date(base + STARS_PERIOD_MS).toISOString());
        if (res) { await runEffects(env, api, cfg, r.user_id, res.effects, res.next, "stars_renewal"); continue; }
        // Duplicate row for today (e.g. cron re-ran): push period forward without re-rewarding.
        await env.DB.prepare("UPDATE memberships SET period_end_at = ? WHERE user_id = ? AND state = 'active'").bind(new Date(base + STARS_PERIOD_MS).toISOString(), r.user_id).run();
        continue;
      }
      const graceUntil = new Date(Date.now() + cfg.graceDays * 86400_000).toISOString();
      const res = await memberStub(env, r.user_id).tryApply(r.user_id, { type: "period_ended", graceUntil }, "cron");
      if (res) await runEffects(env, api, cfg, r.user_id, res.effects, res.next, "period_ended");
    } catch (e) {
      console.error("endPeriods failed", r.user_id, String(e));
    }
  }
}

async function expireGrace(env: Env, api: Api, cfg: Config, now: string) {
  const rows = await env.DB.prepare("SELECT user_id, rail, tier, period_end_at, grace_until FROM memberships WHERE state = 'grace' AND grace_until IS NOT NULL AND grace_until <= ? LIMIT ?")
    .bind(now, BATCH).all<Row>();
  for (const r of rows.results) {
    try {
      const res = await memberStub(env, r.user_id).tryApply(r.user_id, { type: "grace_expired" }, "cron");
      if (res) await runEffects(env, api, cfg, r.user_id, res.effects, res.next, "grace_expired");
    } catch (e) {
      console.error("expireGrace failed", r.user_id, String(e));
    }
  }
}

/** Two DMs per grace window: on entry, and at T+2 days. Guarded by activity_counters(grace_dm_*) keyed on the period end date. */
async function graceReminders(env: Env, api: Api, cfg: Config, now: string) {
  const rows = await env.DB.prepare("SELECT user_id, rail, tier, period_end_at, grace_until FROM memberships WHERE state = 'grace' LIMIT ?").bind(BATCH).all<Row>();
  for (const r of rows.results) {
    try {
      const endDay = (r.period_end_at ?? now).slice(0, 10);
      const untilDay = r.grace_until?.slice(0, 10) ?? "soon";
      const sinceEnd = Date.now() - Date.parse(r.period_end_at ?? now);
      const tier = tierByCode(cfg, r.tier);
      const howTo = r.rail === "stars"
        ? "Renew from Telegram Settings → My Stars → Subscriptions, or send /start for a fresh link."
        : "Update your card or send /start for a fresh checkout link.";
      if ((await bumpCounter(env, r.user_id, endDay, "grace_dm_enter", 1)) !== null) {
        await dm(api, r.user_id, `⏳ Your ${esc(tier?.name ?? "membership")} period has ended. You keep access until <b>${untilDay}</b> — after that the door closes.\n\n${howTo}`);
      } else if (sinceEnd >= 2 * 86400_000 && (await bumpCounter(env, r.user_id, endDay, "grace_dm_t2", 1)) !== null) {
        await dm(api, r.user_id, `🌹 Last call — your access to ${esc(cfg.communityName)} ends <b>${untilDay}</b>.\n\n${howTo}`);
      }
    } catch (e) {
      console.error("graceReminders failed", r.user_id, String(e));
    }
  }
}

async function stillSubscribed(api: Api, channelId: number, userId: number): Promise<boolean> {
  try {
    const m = await api.getChatMember(channelId, userId);
    return m.status === "member" || m.status === "administrator" || m.status === "creator";
  } catch (e) {
    console.warn("getChatMember failed", userId, String(e));
    return false;
  }
}
