/** Shared helpers for the economy module. */
import type { Ctx } from "../../context";
import type { Config } from "../../config";
import { tierByCode } from "../../config";
import type { Env } from "../../env";
import { findMemberByUsername, getMember, type MemberRow } from "../../db";
import { ephemeral } from "../../services/telegram";

export function inGroup(ctx: Ctx): boolean {
  return !!ctx.chat && ctx.cfg.groupChatId !== 0 && ctx.chat.id === ctx.cfg.groupChatId;
}

export function isPrivate(ctx: Ctx): boolean {
  return ctx.chat?.type === "private";
}

/** Reply visible only to the requester: normal reply in DM, ephemeral in the group. */
export async function quietReply(ctx: Ctx, text: string) {
  if (!ctx.chat || !ctx.from) return;
  if (ctx.chat.type === "private") {
    await ctx.reply(text, { parse_mode: "HTML" });
    return;
  }
  await ephemeral(ctx.api, ctx.chat.id, ctx.from.id, text, {
    replyTo: ctx.msg?.message_id, threadId: ctx.msg?.message_thread_id,
  });
}

export interface MembershipLite { state: string; tier: string | null }

export async function getMembership(env: Env, userId: number): Promise<MembershipLite | null> {
  return env.DB.prepare("SELECT state, tier FROM memberships WHERE user_id = ?").bind(userId).first<MembershipLite>();
}

export function isEarning(m: MembershipLite | null): boolean {
  return !!m && (m.state === "active" || m.state === "grace");
}

export function xpMultiplier(cfg: Config, m: MembershipLite | null): number {
  return tierByCode(cfg, m?.tier)?.xpMultiplier ?? 1;
}

/** Resolve "@user" (first arg) or the replied-to message author. */
export async function resolveTarget(ctx: Ctx, args: string[]): Promise<{ member: MemberRow; rest: string[] } | null> {
  const reply = ctx.msg?.reply_to_message?.from;
  if (args[0]?.startsWith("@")) {
    const m = await findMemberByUsername(ctx.env, args[0]);
    return m ? { member: m, rest: args.slice(1) } : null;
  }
  if (reply && !reply.is_bot) {
    const m = await getMember(ctx.env, reply.id);
    return m ? { member: m, rest: args } : null;
  }
  return null;
}

export function argsOf(ctx: Ctx): string[] {
  return (ctx.match ? String(ctx.match) : "").trim().split(/\s+/).filter(Boolean);
}

export function displayName(m: { first_name: string; username: string | null }): string {
  return m.first_name || (m.username ? `@${m.username}` : "member");
}
