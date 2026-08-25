/** Helpers shared by the games and shop modules. */
import type { Config } from "../../config";
import type { Ctx } from "../../context";
import type { Env } from "../../env";

export interface MembershipLite { state: string; tier: string | null }

export async function membershipOf(env: Env, userId: number): Promise<MembershipLite | null> {
  return env.DB.prepare("SELECT state, tier FROM memberships WHERE user_id = ?").bind(userId).first<MembershipLite>();
}

/** Only paying (active) or grace members take part in the economy. */
export async function isEarningMember(env: Env, userId: number): Promise<boolean> {
  const m = await membershipOf(env, userId);
  return m?.state === "active" || m?.state === "grace";
}

export function fmtPoints(cfg: Config, n: number): string {
  return `${n} ${cfg.pointsEmoji} ${cfg.pointsName}`;
}

export function inGroup(ctx: Ctx): boolean {
  return !!ctx.cfg.groupChatId && ctx.chat?.id === ctx.cfg.groupChatId;
}

export function inDm(ctx: Ctx): boolean {
  return ctx.chat?.type === "private";
}

/** Forum topic of the current message, if any. */
export function threadOf(ctx: Ctx): number | undefined {
  const m = ctx.message ?? ctx.callbackQuery?.message;
  return m && "message_thread_id" in m && m.is_topic_message ? m.message_thread_id : undefined;
}

/** Rank of a tier code in cfg.tiers order (-1 if unknown / null). */
export function tierRank(cfg: Config, code: string | null | undefined): number {
  if (!code) return -1;
  return cfg.tiers.findIndex((t) => t.code === code);
}

export function displayName(u: { first_name: string; username?: string | null }): string {
  return u.first_name || (u.username ? `@${u.username}` : "someone");
}
