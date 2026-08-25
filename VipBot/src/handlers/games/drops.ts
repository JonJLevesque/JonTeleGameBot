/** Supply drops: crates, traps, and streak savers. Spawn pacing lives in ChatDO; the
 *  claim is a single atomic UPDATE so concurrent taps yield exactly one winner. */
import type { Api } from "grammy";
import { InlineKeyboard } from "grammy";
import type { Config } from "../../config";
import type { Env } from "../../env";
import { nowIso } from "../../db";
import { signCb } from "../../domain/callbacks";
import type { DropRoll, DropRules } from "../../domain/drops";
import { applyPoints, applyXp, getPoints } from "../../services/ledger";
import { esc, mention } from "../../services/telegram";
import { fmtPoints } from "./common";

export const DROP_TTL_MS = 10 * 60 * 1000;
export const MAX_SAVERS = 2;

export interface DropRow {
  id: number; chat_id: number; message_id: number | null; kind: "crate" | "trap" | "saver";
  points: number; xp: number; spawned_at: string; expires_at: string; claimed_by: number | null; claimed_at: string | null;
}

export function dropRules(cfg: Config): DropRules {
  const e = cfg.economy;
  return { msgMin: e.dropMsgMin, msgMax: e.dropMsgMax, perDay: e.dropsPerDay, min: e.dropMin, max: e.dropMax, xp: e.dropXp, trap: e.dropTrap, saverChance: e.dropSaverChance };
}

/** Public text is identical for every kind — a trap must never be distinguishable before the tap. */
export const DROP_TEXT = "📦 A supply crate dropped. First tap keeps it.";

/** Insert the drop row, post the message with a signed button, and record the message id. */
export async function spawnDrop(env: Env, api: Api, chatId: number, roll: DropRoll, threadId?: number): Promise<number> {
  const t = Date.now();
  const ins = await env.DB.prepare(
    "INSERT INTO drops (chat_id, kind, points, xp, spawned_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
  ).bind(chatId, roll.kind, roll.points, roll.xp, new Date(t).toISOString(), new Date(t + DROP_TTL_MS).toISOString()).run();
  const dropId = Number(ins.meta.last_row_id);
  const kb = new InlineKeyboard().text("Grab it", await signCb(env.CALLBACK_HMAC_KEY, "drop", String(dropId)));
  try {
    const msg = await api.sendMessage(chatId, DROP_TEXT, { reply_markup: kb, message_thread_id: threadId });
    await env.DB.prepare("UPDATE drops SET message_id = ? WHERE id = ?").bind(msg.message_id, dropId).run();
  } catch (e) {
    console.warn("drop send failed", String(e));
  }
  return dropId;
}

export type ClaimOutcome = "won" | "late" | "expired" | "missing";

/** Atomic claim. Exactly one caller can ever get "won" for a given drop. */
export async function claimDrop(env: Env, dropId: number, userId: number): Promise<{ outcome: ClaimOutcome; drop: DropRow | null }> {
  const now = nowIso();
  const upd = await env.DB.prepare(
    "UPDATE drops SET claimed_by = ?, claimed_at = ? WHERE id = ? AND claimed_by IS NULL AND expires_at > ?",
  ).bind(userId, now, dropId, now).run();
  const drop = await env.DB.prepare("SELECT * FROM drops WHERE id = ?").bind(dropId).first<DropRow>();
  if (!drop) return { outcome: "missing", drop: null };
  if ((upd.meta.changes ?? 0) > 0) return { outcome: "won", drop };
  if (drop.claimed_by == null && drop.expires_at <= now) return { outcome: "expired", drop };
  return { outcome: "late", drop };
}

export interface SettleResult { text: string; toast: string; balance: number | null }

/** Move currency for the winner (idempotent on drop id) and build the reveal texts. */
export async function settleDrop(env: Env, cfg: Config, drop: DropRow, winner: { id: number; first_name: string }): Promise<SettleResult> {
  const ref = `drop:${drop.id}`;
  const who = mention(winner.id, winner.first_name);
  switch (drop.kind) {
    case "crate": {
      const r = await applyPoints(env, winner.id, drop.points, "drop", { ref });
      await applyXp(env, winner.id, drop.xp, "drop", ref);
      return {
        text: `📦 ${who} grabbed the crate: <b>+${fmtPoints(cfg, drop.points)}</b> and +${drop.xp} ${cfg.xpEmoji}`,
        toast: `📦 +${fmtPoints(cfg, drop.points)}, +${drop.xp} ${cfg.xpName}. Balance: ${r.balance}.`,
        balance: r.balance,
      };
    }
    case "trap": {
      const loss = Math.abs(drop.points);
      const before = await getPoints(env, winner.id);
      const r = await applyPoints(env, winner.id, -loss, "drop_trap", { ref, clampToZero: true });
      const lost = r.applied ? Math.max(0, before - r.balance) : 0;
      return {
        text: `💥 It was a trap. ${who} lost <b>${fmtPoints(cfg, lost)}</b>.`,
        toast: `💥 Trap! -${fmtPoints(cfg, lost)}. Balance: ${r.balance}.`,
        balance: r.balance,
      };
    }
    case "saver": {
      await env.DB.prepare(
        `INSERT INTO streaks (user_id, savers) VALUES (?, 1)
         ON CONFLICT (user_id) DO UPDATE SET savers = MIN(savers + 1, ?)`,
      ).bind(winner.id, MAX_SAVERS).run();
      await applyXp(env, winner.id, drop.xp, "drop", ref);
      return {
        text: `🛡 ${who} found a <b>streak saver</b> (+${drop.xp} ${cfg.xpEmoji}).`,
        toast: `🛡 Streak saver added (max ${MAX_SAVERS}). +${drop.xp} ${cfg.xpName}.`,
        balance: null,
      };
    }
  }
}

export async function editDropMessage(api: Api, drop: DropRow, text: string) {
  if (!drop.message_id) return;
  try {
    await api.editMessageText(drop.chat_id, drop.message_id, text, { parse_mode: "HTML" });
  } catch (e) {
    console.warn("drop edit failed", String(e));
  }
}

export const EXPIRED_TEXT = esc("📦 The crate is gone. Nobody claimed it.");
