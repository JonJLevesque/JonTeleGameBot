/** Personal invite links: one row per link in `invite_links`, owned by a user. Reused while
 *  unused + unexpired so repeated grant_access calls don't mint a fresh link every time. */
import type { Api } from "grammy";
import type { Config } from "../../config";
import { nowIso } from "../../db";
import type { Env } from "../../env";
import { personalInviteLink } from "../../services/telegram";

export type ChatKind = "group" | "channel";

export interface InviteLinkRow {
  link: string; user_id: number; chat_kind: ChatKind; created_at: string; expires_at: string; used_by: number | null; used_at: string | null;
}

export const LINK_TTL_HOURS = 48;

export function chatIdFor(cfg: Config, kind: ChatKind): number {
  return kind === "group" ? cfg.groupChatId : cfg.channelChatId;
}

export function kindForChat(cfg: Config, chatId: number): ChatKind | null {
  if (chatId && chatId === cfg.groupChatId) return "group";
  if (chatId && chatId === cfg.channelChatId) return "channel";
  return null;
}

export async function findLink(env: Env, link: string): Promise<InviteLinkRow | null> {
  return env.DB.prepare("SELECT * FROM invite_links WHERE link = ?").bind(link).first<InviteLinkRow>();
}

/** Return an unused, unexpired personal link for this user/chat, minting one if needed. */
export async function issueLink(env: Env, api: Api, cfg: Config, kind: ChatKind, userId: number): Promise<string> {
  const chatId = chatIdFor(cfg, kind);
  if (!chatId) throw new Error(`${kind} chat not configured`);
  const t = nowIso();
  const existing = await env.DB.prepare(
    "SELECT * FROM invite_links WHERE user_id = ? AND chat_kind = ? AND used_by IS NULL AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
  ).bind(userId, kind, t).first<InviteLinkRow>();
  if (existing) return existing.link;
  const link = await personalInviteLink(api, chatId, `u${userId}`, LINK_TTL_HOURS);
  await storeLink(env, link, userId, kind, new Date(Date.now() + LINK_TTL_HOURS * 3600_000).toISOString());
  return link;
}

export async function storeLink(env: Env, link: string, userId: number, kind: ChatKind, expiresAt: string) {
  await env.DB.prepare("INSERT OR IGNORE INTO invite_links (link, user_id, chat_kind, created_at, expires_at) VALUES (?, ?, ?, ?, ?)")
    .bind(link, userId, kind, nowIso(), expiresAt).run();
}

export async function markLinkUsed(env: Env, link: string, usedBy: number) {
  await env.DB.prepare("UPDATE invite_links SET used_by = ?, used_at = ? WHERE link = ? AND used_by IS NULL").bind(usedBy, nowIso(), link).run();
}

export async function setPresence(env: Env, userId: number, kind: ChatKind, present: boolean) {
  const col = kind === "group" ? "in_group" : "in_channel";
  await env.DB.prepare(`UPDATE memberships SET ${col} = ? WHERE user_id = ?`).bind(present ? 1 : 0, userId).run();
}
