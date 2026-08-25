/** Payment ingestion for both rails. `payments.external_event_id` is the replay guard:
 *  an event that's already recorded never re-drives the state machine. */
import { Api } from "grammy";
import { loadConfig } from "../../config";
import { nowIso } from "../../db";
import { memberStub } from "../../do/MemberDO";
import type { Env } from "../../env";
import type { PaymentEvent } from "../../services/payments/types";
import { runEffects } from "./effects";

export async function handlePaymentEvent(env: Env, _ctx: ExecutionContext, evt: PaymentEvent, api: Api = new Api(env.TG_BOT_TOKEN)): Promise<{ ok: boolean; note?: string }> {
  const eventId = `${evt.processor}:${evt.eventId}`;
  const ins = await env.DB.prepare(
    `INSERT OR IGNORE INTO payments (user_id, rail, external_event_id, external_txn_id, kind, amount, currency, tier, occurred_at, raw_json)
     VALUES (?, 'external', ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(evt.userId, eventId, evt.txnId ?? null, evt.kind, Math.round(evt.amount), evt.currency, evt.tier, evt.occurredAt, safeJson(evt.raw)).run();
  if ((ins.meta.changes ?? 0) === 0) return { ok: true, note: "duplicate" };

  const stub = memberStub(env, evt.userId);
  const source = `processor:${evt.processor}`;
  const r = evt.kind === "initial" || evt.kind === "rebill"
    ? await stub.tryApply(evt.userId, { type: "payment_ok", rail: "external", tier: evt.tier, periodEndAt: evt.periodEndAt }, source, evt.kind)
    : await stub.tryApply(evt.userId, { type: "reversed" }, source, evt.kind);
  if (!r) return { ok: true, note: "recorded; no state change" };
  if (evt.subscriptionId) {
    await env.DB.prepare("UPDATE memberships SET external_subscription_id = ? WHERE user_id = ?").bind(evt.subscriptionId, evt.userId).run();
  }
  const cfg = await loadConfig(env);
  await runEffects(env, api, cfg, evt.userId, r.effects, r.next, `payment:${evt.kind}`);
  return { ok: true, note: `${r.before.state} -> ${r.next.state}` };
}

/** Stars channel subscription observed (join, or still-a-member at period end). One row per user per day. */
export async function recordStarsSubscription(env: Env, userId: number, tier: string, stars: number, periodEndAt: string, link?: string) {
  const day = nowIso().slice(0, 10);
  const ins = await env.DB.prepare(
    `INSERT OR IGNORE INTO payments (user_id, rail, external_event_id, external_txn_id, kind, amount, currency, tier, occurred_at, raw_json)
     VALUES (?, 'stars', ?, NULL, 'stars_sub', ?, 'XTR', ?, ?, ?)`,
  ).bind(userId, `tgsub:${userId}:${day}`, stars, tier, nowIso(), link ? JSON.stringify({ link }) : null).run();
  if ((ins.meta.changes ?? 0) === 0) return null;
  return memberStub(env, userId).tryApply(userId, { type: "payment_ok", rail: "stars", tier, periodEndAt }, "telegram", "stars_sub");
}

function safeJson(v: unknown): string | null {
  try { return v == null ? null : JSON.stringify(v).slice(0, 4000); } catch { return null; }
}
