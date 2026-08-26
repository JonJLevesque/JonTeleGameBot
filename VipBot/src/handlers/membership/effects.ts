/** Executes the side effects the membership FSM emits. Every effect is safe to re-run:
 *  links are reused, kicks/bans are naturally idempotent, rewards are keyed by ref. */
import type { Api } from "grammy";
import { InlineKeyboard } from "grammy";
import { tierAllowsGroup, tierByCode, type Config } from "../../config";
import { signCb } from "../../domain/callbacks";
import type { Effect, MemberSnapshot } from "../../domain/membership";
import { memberStub } from "../../do/MemberDO";
import type { Env } from "../../env";
import { applyPoints, applyXp } from "../../services/ledger";
import { ban, dm, esc } from "../../services/telegram";
import { issueLink, setPresence } from "./links";

export const RENEWAL_XP = 200;

/** True when both target chats are configured. Otherwise nags admins (once per day) and returns false. */
export async function setupReady(env: Env, api: Api, cfg: Config): Promise<boolean> {
  if (cfg.groupChatId && cfg.channelChatId) return true;
  const key = "setup:nagged";
  const already = await env.KV.get(key).catch(() => null);
  if (!already) {
    await env.KV.put(key, "1", { expirationTtl: 86400 }).catch(() => {});
    const missing = [!cfg.groupChatId && "group", !cfg.channelChatId && "channel"].filter(Boolean).join(" and ");
    for (const id of env.ADMIN_USER_IDS.split(",").map((s) => Number(s.trim())).filter(Boolean)) {
      await dm(api, id, `⚠️ A member tried to join but the ${esc(missing)} chat isn't configured yet. Run /setup to finish.`);
    }
  }
  return false;
}

/** Link reveal: group join-request link always; channel link too for the external rail
 *  (Stars members enter the channel through their subscription link). */
export async function grantAccess(env: Env, api: Api, cfg: Config, userId: number, snap?: MemberSnapshot): Promise<boolean> {
  if (!(await setupReady(env, api, cfg))) {
    await dm(api, userId, "You're all set on our side, but the creator hasn't finished setting up the rooms yet. You'll get your links as soon as they do. 🌸");
    return false;
  }
  const s = snap ?? (await memberStub(env, userId).snapshot(userId));
  const tier = tierByCode(cfg, s.tier);
  const lines = [
    `${tier?.emoji ?? "🌸"} <b>Welcome to ${esc(cfg.communityName)}${tier ? ` · ${esc(tier.name)}` : ""}.</b>`,
  ];
  if (s.rail === "external") {
    const channel = await issueLink(env, api, cfg, "channel", userId);
    lines.push("", "📸 <b>The feed</b> (exclusive posts):", channel);
  } else {
    lines.push("", "📸 <b>The feed</b>: you're in through your subscription link.");
  }
  if (tierAllowsGroup(cfg, s.tier)) {
    const group = await issueLink(env, api, cfg, "group", userId);
    lines.push("", `💬 <b>The room</b> (chat, games, ${esc(cfg.pointsName)}):`, group);
  } else {
    const upgrade = cfg.tiers.find((t) => t.group);
    if (upgrade) lines.push("", `💬 The room (chat, games, ${esc(cfg.pointsName)}) is ${upgrade.emoji} ${esc(upgrade.name)} only — /start any time to upgrade.`);
  }
  if (s.rail === "external" || tierAllowsGroup(cfg, s.tier)) {
    lines.push("", "These links are yours alone: each works once and expires in 48 hours. Tap, request to join, and you're in within seconds.");
  }
  // A downgrade (VIP+ → VIP) revokes the room without touching the feed.
  if (!tierAllowsGroup(cfg, s.tier)) {
    const row = await env.DB.prepare("SELECT in_group FROM memberships WHERE user_id = ?").bind(userId).first<{ in_group: number }>();
    if (row?.in_group) {
      await env.TG_OPS.send({ kind: "kick", userId, reason: "tier_no_group", chats: ["group"] });
      await setPresence(env, userId, "group", false);
    }
  }
  await dm(api, userId, lines.join("\n"), { link_preview_options: { is_disabled: true } });
  return true;
}

export async function revokeAccess(env: Env, api: Api, cfg: Config, userId: number, opts: { ban: boolean; reason: string }) {
  if (opts.ban) {
    for (const chat of [cfg.groupChatId, cfg.channelChatId]) {
      if (chat) await ban(api, chat, userId).catch((e) => console.warn("ban failed", chat, String(e)));
    }
  } else {
    await env.TG_OPS.send({ kind: "kick", userId, reason: opts.reason });
  }
  await setPresence(env, userId, "group", false);
  await setPresence(env, userId, "channel", false);
}

export async function winbackDm(env: Env, api: Api, cfg: Config, userId: number) {
  const kb = new InlineKeyboard().text("Come back 🌹", await signCb(env.CALLBACK_HMAC_KEY, "fn", "start"));
  await dm(api, userId,
    `Your ${esc(cfg.communityName)} membership has ended and the door has closed behind you — but it isn't locked.\n\nTap below (or send /start) whenever you want back in.`,
    { reply_markup: kb });
}

export async function renewalReward(env: Env, cfg: Config, userId: number, snap: MemberSnapshot) {
  const tier = tierByCode(cfg, snap.tier);
  const ref = `renewal:${userId}:${snap.periodEndAt ?? "unknown"}`;
  if (tier && tier.renewalPoints > 0) await applyPoints(env, userId, tier.renewalPoints, "renewal", { ref });
  await applyXp(env, userId, RENEWAL_XP, "renewal", ref);
}

/** Run FSM effects for a user. `snap` should be the post-transition snapshot when available. */
export async function runEffects(env: Env, api: Api, cfg: Config, userId: number, effects: Effect[], snap?: MemberSnapshot, reason = "membership") {
  for (const e of effects) {
    try {
      switch (e.kind) {
        case "grant_access": await grantAccess(env, api, cfg, userId, snap); break;
        case "revoke_access": await revokeAccess(env, api, cfg, userId, { ban: e.ban, reason }); break;
        case "winback_dm": await winbackDm(env, api, cfg, userId); break;
        case "renewal_reward": {
          const s = snap ?? (await memberStub(env, userId).snapshot(userId));
          await renewalReward(env, cfg, userId, s);
          const tier = tierByCode(cfg, s.tier);
          if (tier) await dm(api, userId, `${tier.emoji} Renewed. +${tier.renewalPoints} ${esc(cfg.pointsName)} and +${RENEWAL_XP} ${esc(cfg.xpName)} for staying. See you inside.`);
          break;
        }
      }
    } catch (err) {
      console.error("effect failed", e.kind, userId, String(err));
    }
  }
}
