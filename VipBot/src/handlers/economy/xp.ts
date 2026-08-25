/** Passive XP: message XP (middleware, always calls next) and reactions received. */
import type { Bot } from "grammy";
import type { Ctx } from "../../context";
import type { Env } from "../../env";
import { bumpCounter } from "../../db";
import { applyPoints, applyXp } from "../../services/ledger";
import { titleFor } from "../../domain/levels";
import { EFFECT, ephemeral, groupSay, mention } from "../../services/telegram";
import { getMembership, inGroup, isEarning, xpMultiplier } from "./common";

const LASTMSG_TTL = 3600;
const AUTHOR_TTL = 48 * 3600;

export const lastMsgKey = (uid: number) => `lastmsg:${uid}`;
export const msgAuthorKey = (chatId: number, msgId: number) => `msgauthor:${chatId}:${msgId}`;

/** Hash of normalized text. We never store message bodies. */
export async function textHash(text: string): Promise<string> {
  const norm = text.toLowerCase().replace(/\s+/g, " ").trim();
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(norm));
  return Array.from(new Uint8Array(buf).slice(0, 12)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

/** Announce a level-up publicly and DM-style the unlock. Safe to call with null. */
export async function announceLevelUp(ctx: Ctx, userId: number, name: string, level: number | null) {
  if (!level) return;
  const t = titleFor(level);
  ctx.defer(groupSay(ctx.api, ctx.cfg, `🔥 ${mention(userId, name)} rose to <b>Level ${level} — ${t.title}</b>.`, { effectId: EFFECT.fire }));
  if (t.unlock && ctx.cfg.groupChatId) {
    ctx.defer(ephemeral(ctx.api, ctx.cfg.groupChatId, userId, `🔓 Level ${level} unlock: ${t.unlock}`));
  }
}

/** Pure-ish core so tests can drive it without a Telegram update. */
export async function awardMessageXp(env: Env, ctx: Ctx, userId: number, chatId: number, messageId: number, text: string): Promise<number | null> {
  if (wordCount(text) < 3) return null;
  const hash = await textHash(text);
  const key = lastMsgKey(userId);
  const prev = await env.KV.get(key);
  await env.KV.put(key, hash, { expirationTtl: LASTMSG_TTL });
  if (prev === hash) return null;
  const m = await getMembership(env, userId);
  if (!isEarning(m)) return null;
  const eco = ctx.cfg.economy;
  const n = await bumpCounter(env, userId, ctx.day, "msg_xp", eco.messageXpDailyCap, eco.messageXpCooldownSec);
  if (n === null) return null;
  const xp = Math.round(eco.messageXp * xpMultiplier(ctx.cfg, m));
  const r = await applyXp(env, userId, xp, "msg", `${chatId}:${messageId}`);
  return r.applied ? r.leveledUpTo ?? 0 : null;
}

export async function awardReaction(env: Env, ctx: Ctx, authorId: number, reactorId: number, chatId: number, messageId: number): Promise<boolean> {
  if (authorId === reactorId) return false;
  const eco = ctx.cfg.economy;
  const n = await bumpCounter(env, authorId, ctx.day, "react_recv", eco.reactionDailyCap);
  if (n === null) return false;
  const ref = `react:${chatId}:${messageId}:${reactorId}`;
  const xp = await applyXp(env, authorId, eco.reactionXp, "reaction", ref);
  if (!xp.applied) return false;
  await applyPoints(env, authorId, eco.reactionPoints, "reaction", { ref });
  const author = await env.DB.prepare("SELECT first_name FROM members WHERE user_id = ?").bind(authorId).first<{ first_name: string }>();
  await announceLevelUp(ctx, authorId, author?.first_name ?? "someone", xp.leveledUpTo);
  return true;
}

export function registerXp(bot: Bot<Ctx>) {
  // Message XP middleware: records author, awards XP, always continues to games/shop.
  bot.on("message", async (ctx, next) => {
    try {
      const from = ctx.from;
      const msg = ctx.msg;
      if (inGroup(ctx) && from && !from.is_bot && msg) {
        ctx.defer(ctx.env.KV.put(msgAuthorKey(ctx.chat.id, msg.message_id), String(from.id), { expirationTtl: AUTHOR_TTL }));
        if (msg.text && !msg.text.startsWith("/")) {
          const chatId = ctx.chat.id;
          ctx.defer((async () => {
            const lvl = await awardMessageXp(ctx.env, ctx, from.id, chatId, msg.message_id, msg.text!);
            await announceLevelUp(ctx, from.id, from.first_name, lvl || null);
          })());
        }
      }
    } catch (e) {
      console.warn("msg xp failed", String(e));
    }
    await next();
  });

  bot.on("message_reaction", async (ctx, next) => {
    const r = ctx.messageReaction;
    const reactor = r.user;
    if (inGroup(ctx) && reactor && !reactor.is_bot && r.new_reaction.length > r.old_reaction.length) {
      const chatId = r.chat.id;
      ctx.defer((async () => {
        const author = await ctx.env.KV.get(msgAuthorKey(chatId, r.message_id));
        if (!author) return;
        await awardReaction(ctx.env, ctx, Number(author), reactor.id, chatId, r.message_id);
      })());
    }
    await next();
  });
}
