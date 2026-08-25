/** Test harness: real bot + real D1/DO, Telegram API replaced by a recording transformer. */
import { env } from "cloudflare:test";
import type { Api, Bot } from "grammy";
import type { Update, UserFromGetMe } from "grammy/types";
import { createBot } from "../src/bot";
import type { Ctx } from "../src/context";
import type { Env } from "../src/env";

export interface Call { method: string; payload: Record<string, unknown> }

export interface Recorder {
  calls: Call[];
  /** Override a method's canned result (or throw by returning an Error). */
  results: Record<string, (payload: Record<string, unknown>) => unknown>;
  of(method: string): Call[];
  last(method: string): Record<string, unknown> | undefined;
  reset(): void;
}

let linkSeq = 0;
export function record(api: Api): Recorder {
  const rec: Recorder = {
    calls: [], results: {},
    of(m) { return this.calls.filter((c) => c.method === m); },
    last(m) { return this.of(m).at(-1)?.payload; },
    reset() { this.calls = []; },
  };
  api.config.use(async (_prev, method, payload) => {
    rec.calls.push({ method, payload: payload as Record<string, unknown> });
    const custom = rec.results[method];
    if (custom) {
      const r = custom(payload as Record<string, unknown>);
      if (r instanceof Error) return { ok: false, error_code: 400, description: r.message };
      return { ok: true, result: r } as never;
    }
    return { ok: true, result: canned(method, payload as Record<string, unknown>) } as never;
  });
  return rec;
}

function canned(method: string, p: Record<string, unknown>): unknown {
  switch (method) {
    case "getMe": return BOT_USER;
    case "sendMessage": return { message_id: 1000 + Math.floor(Math.random() * 1e6), date: 0, chat: { id: p.chat_id, type: "private" }, text: p.text };
    case "createChatInviteLink": return { invite_link: `https://t.me/+inv${++linkSeq}`, creator: BOT_USER, creates_join_request: true, is_primary: false, is_revoked: false, name: p.name };
    case "createChatSubscriptionInviteLink": return { invite_link: `https://t.me/+sub${++linkSeq}`, creator: BOT_USER, creates_join_request: false, is_primary: false, is_revoked: false, subscription_period: 2592000, subscription_price: p.subscription_price };
    case "getChatMember": return { status: "left", user: { id: p.user_id, is_bot: false, first_name: "x" } };
    default: return true;
  }
}

export const BOT_USER: UserFromGetMe = { id: 42, is_bot: true, first_name: "VipBot", username: "vip_test_bot", can_join_groups: true, can_read_all_group_messages: false, supports_inline_queries: false, can_connect_to_business: false, has_main_web_app: false, has_topics_enabled: false, allows_users_to_create_topics: false, can_manage_bots: false, supports_join_request_queries: true };
export const GROUP = -1001000000001;
export const CHANNEL = -1001000000002;

export async function makeBot(): Promise<{ bot: Bot<Ctx>; rec: Recorder }> {
  const bot = await createBot(env as unknown as Env, { waitUntil() {}, passThroughOnException() {}, props: {} } as unknown as ExecutionContext);
  bot.botInfo = BOT_USER;
  const rec = record(bot.api);
  return { bot, rec };
}

let updSeq = 1;
export const user = (id: number, first = `U${id}`) => ({ id, is_bot: false, first_name: first, username: `user${id}`, language_code: "en" });

export function dmUpdate(uid: number, text: string): Update {
  const cmd = text.startsWith("/") ? [{ type: "bot_command" as const, offset: 0, length: text.split(" ")[0]!.length }] : [];
  return { update_id: updSeq++, message: { message_id: updSeq, date: 0, chat: { id: uid, type: "private", first_name: `U${uid}` }, from: user(uid), text, entities: cmd } };
}

export function cbUpdate(uid: number, data: string): Update {
  return { update_id: updSeq++, callback_query: { id: `q${updSeq}`, from: user(uid), chat_instance: "ci", data, message: { message_id: 1, date: 0, chat: { id: uid, type: "private", first_name: `U${uid}` }, text: "…" } } };
}

export function joinRequestUpdate(uid: number, chatId: number, link?: { invite_link: string; subscription_price?: number }, queryId?: string): Update {
  return {
    update_id: updSeq++,
    chat_join_request: {
      chat: chatId === CHANNEL ? { id: chatId, type: "channel", title: "feed" } : { id: chatId, type: "supergroup", title: "room" },
      from: user(uid), user_chat_id: uid, date: 0, query_id: queryId,
      invite_link: link ? { ...link, creator: BOT_USER, creates_join_request: !link.subscription_price, is_primary: false, is_revoked: false } : undefined,
    },
  } as unknown as Update;
}

export function chatMemberUpdate(uid: number, chatId: number, from: "left" | "member" | "kicked", to: "left" | "member" | "kicked", link?: { invite_link: string; subscription_price?: number }): Update {
  const u = user(uid);
  const mk = (status: string) => (status === "kicked" ? { status, user: u, until_date: 0 } : { status, user: u });
  return {
    update_id: updSeq++,
    chat_member: {
      chat: chatId === CHANNEL ? { id: chatId, type: "channel", title: "feed" } : { id: chatId, type: "supergroup", title: "room" },
      from: u, date: 0, old_chat_member: mk(from), new_chat_member: mk(to),
      invite_link: link ? { ...link, creator: BOT_USER, creates_join_request: false, is_primary: false, is_revoked: false } : undefined,
    },
  } as unknown as Update;
}

/** All callback_data values from the inline keyboard of a sendMessage payload. */
export function buttons(p: Record<string, unknown> | undefined): { text: string; data: string }[] {
  const kb = (p?.reply_markup as { inline_keyboard?: { text: string; callback_data?: string }[][] } | undefined)?.inline_keyboard ?? [];
  return kb.flat().filter((b) => b.callback_data).map((b) => ({ text: b.text, data: b.callback_data! }));
}
