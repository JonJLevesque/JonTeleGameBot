/** Thin wrappers over the Bot API for things grammY's sugar doesn't cover well. */
import type { Api } from "grammy";
import type { Config } from "../config";

export const EFFECT = { fire: "5104841245755180586", party: "5046509860389126442", heart: "5159385139981059251", thumbs: "5107584321108051014" } as const;

/** Ephemeral message: visible only to `userId` inside the group. Falls back to nothing if unsupported. */
export async function ephemeral(api: Api, chatId: number, userId: number, text: string, opts: { callbackQueryId?: string; threadId?: number; replyTo?: number } = {}) {
  try {
    await api.raw.sendMessage({
      chat_id: chatId, receiver_user_id: userId, text, parse_mode: "HTML",
      callback_query_id: opts.callbackQueryId, message_thread_id: opts.threadId,
      reply_parameters: opts.replyTo ? { message_id: opts.replyTo } : undefined,
    });
  } catch (e) {
    console.warn("ephemeral failed", String(e));
  }
}

export async function groupSay(api: Api, cfg: Config, text: string, opts: { effectId?: string; threadId?: number | null } = {}) {
  if (!cfg.groupChatId) return null;
  return api.sendMessage(cfg.groupChatId, text, {
    parse_mode: "HTML", message_effect_id: opts.effectId, message_thread_id: opts.threadId ?? undefined,
  });
}

export async function dm(api: Api, userId: number, text: string, extra: Parameters<Api["sendMessage"]>[2] = {}) {
  try {
    return await api.sendMessage(userId, text, { parse_mode: "HTML", ...extra });
  } catch (e) {
    console.warn("dm failed", userId, String(e));
    return null;
  }
}

/** Kick = ban then unban so the user can come back through a fresh link. */
export async function kick(api: Api, chatId: number, userId: number) {
  await api.banChatMember(chatId, userId);
  await api.unbanChatMember(chatId, userId, { only_if_banned: true });
}

export async function ban(api: Api, chatId: number, userId: number) {
  await api.banChatMember(chatId, userId);
}

export async function unban(api: Api, chatId: number, userId: number) {
  await api.unbanChatMember(chatId, userId, { only_if_banned: true });
}

/** Single-use, join-request-gated invite link for one user. */
export async function personalInviteLink(api: Api, chatId: number, name: string, ttlHours = 48) {
  const link = await api.createChatInviteLink(chatId, {
    name: name.slice(0, 32), creates_join_request: true, expire_date: Math.floor(Date.now() / 1000) + ttlHours * 3600,
  });
  return link.invite_link;
}

/** Stars subscription link for the channel (30 days, price in Stars). Telegram bills and auto-removes. */
export async function starsSubscriptionLink(api: Api, chatId: number, name: string, stars: number) {
  const link = await api.raw.createChatSubscriptionInviteLink({
    chat_id: chatId, name: name.slice(0, 32), subscription_period: 2592000, subscription_price: stars,
  });
  return link.invite_link;
}

export function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function mention(userId: number, name: string): string {
  return `<a href="tg://user?id=${userId}">${esc(name)}</a>`;
}
