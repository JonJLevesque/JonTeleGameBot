/** Membership events from Telegram: join requests on personal links, channel joins via Stars
 *  subscription links, presence tracking, and the public welcome ritual. */
import { redeemLobbyPetals } from "../lobby";
import { tierAllowsGroup } from "../../config";
import type { Bot } from "grammy";
import type { ChatInviteLink, ChatMemberUpdated } from "grammy/types";
import type { Config } from "../../config";
import type { Ctx } from "../../context";
import { audit, nowIso } from "../../db";
import { isActive } from "../../domain/membership";
import { memberStub } from "../../do/MemberDO";
import type { Env } from "../../env";
import { applyPoints } from "../../services/ledger";
import { dm, EFFECT, ephemeral, esc, groupSay, mention } from "../../services/telegram";
import { runEffects } from "./effects";
import { findLink, kindForChat, markLinkUsed, setPresence } from "./links";
import { recordStarsSubscription } from "./payments";

const IN = new Set(["member", "administrator", "creator", "restricted"]);
const isIn = (m: ChatMemberUpdated["new_chat_member"]) => IN.has(m.status) && !("is_member" in m && m.is_member === false);

export function registerMembership(bot: Bot<Ctx>) {
  bot.on("chat_join_request", async (ctx) => {
    try { await onJoinRequest(ctx); } catch (e) { console.error("join_request failed", String(e)); }
  });
  bot.on("chat_member", async (ctx) => {
    try { await onChatMember(ctx); } catch (e) { console.error("chat_member failed", String(e)); }
  });
}

async function onJoinRequest(ctx: Ctx) {
  const req = ctx.chatJoinRequest!;
  const kind = kindForChat(ctx.cfg, req.chat.id);
  if (!kind) return;
  const uid = req.from.id;
  const link = req.invite_link?.invite_link;
  const row = link ? await findLink(ctx.env, link) : null;
  const snap = await memberStub(ctx.env, uid).snapshot(uid);

  let ok = false;
  if (row && row.user_id !== uid) {
    await audit(ctx.env, uid, "link_shared", row.user_id, { link_owner: row.user_id, used_by: uid, chat: kind });
  } else if (row && row.used_by != null && row.used_by !== uid) {
    await audit(ctx.env, uid, "link_shared", row.user_id, { link_owner: row.user_id, used_by: uid, consumed_by: row.used_by, chat: kind });
  } else if (isActive(snap.state) && (row || isStarsLink(req.invite_link))) {
    ok = kind === "channel" || tierAllowsGroup(ctx.cfg, snap.tier);
  }

  const answer = async (result: "approve" | "decline") => {
    if (req.query_id) return ctx.api.raw.answerChatJoinRequestQuery({ chat_join_request_query_id: req.query_id, result });
    return result === "approve" ? ctx.api.approveChatJoinRequest(req.chat.id, uid) : ctx.api.declineChatJoinRequest(req.chat.id, uid);
  };

  if (ok) {
    await answer("approve");
    if (link) await markLinkUsed(ctx.env, link, uid);
    await setPresence(ctx.env, uid, kind, true);
  } else {
    await answer("decline").catch((e) => console.warn("decline failed", String(e)));
    await dm(ctx.api, uid, `That link isn't valid for your account. Send /start and I'll get you sorted. 🌸`);
  }
}

async function onChatMember(ctx: Ctx) {
  const upd = ctx.chatMember!;
  const kind = kindForChat(ctx.cfg, upd.chat.id);
  if (!kind) return;
  const user = upd.new_chat_member.user;
  if (user.is_bot) return;
  const uid = user.id;
  const wasIn = isIn(upd.old_chat_member);
  const nowIn = isIn(upd.new_chat_member);
  if (wasIn === nowIn) return;

  await setPresence(ctx.env, uid, kind, nowIn);

  if (kind === "channel") {
    if (nowIn) {
      if (isStarsLink(upd.invite_link)) await onStarsJoin(ctx.env, ctx, ctx.cfg, uid, upd.invite_link!);
    } else {
      // Telegram removed (or the user left) a Stars subscriber: end the period now; reconcile takes it from here.
      const snap = await memberStub(ctx.env, uid).snapshot(uid);
      if (snap.rail === "stars" && snap.state === "active") {
        await ctx.env.DB.prepare("UPDATE memberships SET period_end_at = ? WHERE user_id = ? AND state = 'active'").bind(nowIso(), uid).run();
      }
    }
    return;
  }

  if (kind === "group" && nowIn) await welcome(ctx, uid, user.first_name);
}

async function onStarsJoin(env: Env, ctx: Ctx, cfg: Config, uid: number, link: ChatInviteLink) {
  const price = link.subscription_price ?? 0;
  const tier = cfg.tiers.find((t) => t.stars === price) ?? cfg.tiers[0];
  if (!tier) return;
  if (!cfg.tiers.some((t) => t.stars === price)) console.warn("stars join with unknown price", uid, price);
  const periodEndAt = new Date(Date.now() + 30 * 86400_000).toISOString();
  const r = await recordStarsSubscription(env, uid, tier.code, price, periodEndAt, link.invite_link);
  if (!r) return; // duplicate event
  await runEffects(env, ctx.api, cfg, uid, r.effects, r.next, "stars_subscription");
}

/** First group join: public ritual + ephemeral how-to + welcome points. Everything keyed on welcome:<uid>. */
async function welcome(ctx: Ctx, uid: number, firstName: string) {
  const { env, cfg } = ctx;
  const pts = await applyPoints(env, uid, cfg.welcomePoints, "welcome", { ref: `welcome:${uid}` });
  const banked = await redeemLobbyPetals(env, uid);
  if (!pts.applied) return; // been here before
  await groupSay(ctx.api, cfg, `🌹 A new petal falls. Welcome ${mention(uid, firstName)}.`, { effectId: EFFECT.party });
  await ephemeral(ctx.api, cfg.groupChatId, uid,
    `Welcome in. Quick start:\n• <b>/claim</b> — daily ${cfg.pointsEmoji} ${esc(cfg.pointsName)} (streaks pay more)\n• Chat to earn ${cfg.xpEmoji} ${esc(cfg.xpName)} and level up\n• <b>/profile</b> — see where you stand\n\nYou start with ${cfg.welcomePoints + banked} ${esc(cfg.pointsName)}${banked ? ` — ${banked} of them you banked in ${esc(cfg.roomNames.lobby)}` : ""}. 🌸`);
}

function isStarsLink(link: ChatInviteLink | undefined): boolean {
  return !!link && typeof link.subscription_price === "number" && link.subscription_price > 0;
}
