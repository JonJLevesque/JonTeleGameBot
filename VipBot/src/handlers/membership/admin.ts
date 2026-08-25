/** Admin-facing membership operations. Callers (the admin module) gate on ctx.isAdmin;
 *  these functions just do the work and write the audit trail. */
import type { Api } from "grammy";
import type { Config } from "../../config";
import { audit, nowIso } from "../../db";
import type { MemberSnapshot } from "../../domain/membership";
import { memberStub } from "../../do/MemberDO";
import type { Env } from "../../env";
import { unban } from "../../services/telegram";
import { runEffects } from "./effects";

export interface AdminResult { ok: boolean; note: string; snapshot?: MemberSnapshot }

/** Remove from both chats. Active members are walked through grace → lapsed so they get the win-back DM and can return. */
export async function adminKick(env: Env, api: Api, cfg: Config, actorId: number, userId: number, reason: string): Promise<AdminResult> {
  const stub = memberStub(env, userId);
  const ended = await stub.tryApply(userId, { type: "period_ended", graceUntil: nowIso() }, `admin:${actorId}`, `kick: ${reason}`);
  const lapsed = await stub.tryApply(userId, { type: "grace_expired" }, `admin:${actorId}`, `kick: ${reason}`);
  if (lapsed) {
    await runEffects(env, api, cfg, userId, lapsed.effects, lapsed.next, `admin_kick: ${reason}`);
  } else {
    await runEffects(env, api, cfg, userId, [{ kind: "revoke_access", ban: false }], undefined, `admin_kick: ${reason}`);
  }
  await audit(env, actorId, "admin_kick", userId, { reason });
  const snapshot = await stub.snapshot(userId);
  return { ok: true, note: `${ended?.before.state ?? snapshot.state} -> ${snapshot.state}`, snapshot };
}

export async function adminBan(env: Env, api: Api, cfg: Config, actorId: number, userId: number, reason: string): Promise<AdminResult> {
  const stub = memberStub(env, userId);
  const r = await stub.tryApply(userId, { type: "ban" }, `admin:${actorId}`, reason);
  if (!r) return { ok: false, note: "could not ban (unexpected state)" };
  await runEffects(env, api, cfg, userId, r.effects, r.next, `admin_ban: ${reason}`);
  await audit(env, actorId, "admin_ban", userId, { reason });
  return { ok: true, note: `${r.before.state} -> ${r.next.state}`, snapshot: r.next };
}

export async function adminUnban(env: Env, api: Api, cfg: Config, actorId: number, userId: number, reason = ""): Promise<AdminResult> {
  const stub = memberStub(env, userId);
  const r = await stub.tryApply(userId, { type: "unban" }, `admin:${actorId}`, reason || "unban");
  if (!r) return { ok: false, note: "user is not banned" };
  for (const chat of [cfg.groupChatId, cfg.channelChatId]) {
    if (chat) await unban(api, chat, userId).catch((e) => console.warn("unban failed", chat, String(e)));
  }
  await audit(env, actorId, "admin_unban", userId, { reason });
  return { ok: true, note: `${r.before.state} -> ${r.next.state}; they can /start again`, snapshot: r.next };
}

/**
 * Refund the latest Stars payment we hold a charge id for. Limitation: channel subscriptions
 * bought through a subscription invite link are billed and refunded by Telegram itself — the
 * bot never sees a `telegram_payment_charge_id` for them, so this only works for Stars
 * payments made through the bot (tips/purchases recorded with a charge id in payments.external_txn_id).
 */
export async function adminRefundStars(env: Env, api: Api, _cfg: Config, actorId: number, userId: number, reason = ""): Promise<AdminResult> {
  const p = await env.DB.prepare(
    "SELECT id, external_txn_id, amount FROM payments WHERE user_id = ? AND rail = 'stars' AND external_txn_id IS NOT NULL ORDER BY occurred_at DESC LIMIT 1",
  ).bind(userId).first<{ id: number; external_txn_id: string; amount: number }>();
  if (!p) return { ok: false, note: "no refundable Stars payment on file (channel subscriptions are refunded by Telegram, not the bot)" };
  try {
    await api.refundStarPayment(userId, p.external_txn_id);
  } catch (e) {
    return { ok: false, note: `refund failed: ${String(e)}` };
  }
  await audit(env, actorId, "admin_refund_stars", userId, { payment_id: p.id, charge_id: p.external_txn_id, amount: p.amount, reason });
  return { ok: true, note: `refunded ⭐${p.amount} (charge ${p.external_txn_id})` };
}

export type MemberFilter = "active" | "grace" | "lapsed" | "all";
export interface MemberListRow {
  user_id: number; username: string | null; first_name: string; state: string; rail: string | null; tier: string | null;
  period_end_at: string | null; grace_until: string | null; in_group: number; in_channel: number;
}

export async function listMembers(env: Env, filter: MemberFilter, limit = 100): Promise<MemberListRow[]> {
  const where = filter === "all" ? "" : "WHERE ms.state = ?";
  const stmt = env.DB.prepare(
    `SELECT ms.user_id, m.username, COALESCE(m.first_name, '') AS first_name, ms.state, ms.rail, ms.tier, ms.period_end_at, ms.grace_until, ms.in_group, ms.in_channel
     FROM memberships ms LEFT JOIN members m ON m.user_id = ms.user_id ${where}
     ORDER BY ms.last_transition_at DESC LIMIT ?`,
  );
  const r = filter === "all" ? await stmt.bind(limit).all<MemberListRow>() : await stmt.bind(filter, limit).all<MemberListRow>();
  return r.results;
}
