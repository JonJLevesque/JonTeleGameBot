/** DM onboarding: /start → pitch → attestation → tier → rail → payment link → (membership module grants access). */
import { InlineKeyboard, type Bot } from "grammy";
import { tierByCode, type Config, tierAccessLabel } from "../../config";
import type { Ctx } from "../../context";
import { nowIso, upsertMember } from "../../db";
import { signCb, verifyCb } from "../../domain/callbacks";
import { isActive, type MemberSnapshot, type Rail } from "../../domain/membership";
import { memberStub } from "../../do/MemberDO";
import type { Env } from "../../env";
import { PROCESSORS } from "../../services/payments/fake";
import { dm, ephemeral, esc, starsSubscriptionLink } from "../../services/telegram";
import { setupReady } from "../membership/effects";
import { storeLink } from "../membership/links";

export const CB_KIND = "fn";
export const ATTESTATION_TEXT =
  "By continuing you confirm: (1) I am 18 or older and of legal age in my location; (2) I consent to viewing adult content; (3) I will not screenshot, record, or redistribute anything from this community. Violations end membership without refund.";
export const ATTEST_BUTTON = "I confirm all three";
const STARS_PERIOD_DAYS = 30;

const cb = (env: Env, payload: string) => signCb(env.CALLBACK_HMAC_KEY, CB_KIND, payload);

export function registerFunnel(bot: Bot<Ctx>) {
  const priv = bot.chatType("private");

  bot.command("help", async (ctx) => {
    const c = ctx.cfg;
    const text =
      `<b>${esc(c.communityName)}</b>\n\n` +
      `<b>Membership</b>\n/start — join, or see your status\n\n` +
      `<b>Every member</b>\n/claim — daily ${esc(c.pointsName)} (streaks pay more)\n/profile — level, ${esc(c.xpName)}, ${esc(c.pointsName)}, badges\n/tip &lt;stars&gt; — tip with Telegram Stars\n\n` +
      `<b>In the room</b> (${c.tiers.filter((t) => t.group).map((t) => `${t.emoji} ${esc(t.name)}`).join(", ") || "room tiers"})\nChat to earn ${esc(c.xpName)}. Tap crates when they drop. Trivia at 20:00.\n/leaderboard [xp|points|streak]\n/slots &lt;stake&gt; — in the games topic\n/give @user &lt;n&gt; — share ${esc(c.pointsName)}\n/shop — titles, shoutouts, perks`;
    const admin = ctx.isAdmin && ctx.chat?.type === "private"
      ? "\n\n<b>Creator</b>\nJust ask me in plain words — “how do I comp someone?” — or /request &lt;idea&gt; to send Jon a feature request."
      : "";
    if (ctx.chat?.type === "private") await ctx.reply(text + admin, { parse_mode: "HTML" });
    else if (ctx.from) await ephemeral(ctx.api, ctx.chat!.id, ctx.from.id, text);
  });

  priv.command("start", async (ctx) => {
    const ref = parseRef(ctx.match);
    if (ref && ctx.from && ref !== ctx.from.id) await recordReferrer(ctx.env, ctx.from, ref);
    await start(ctx);
  });

  priv.on("callback_query:data", async (ctx, next) => {
    const v = await verifyCb(ctx.env.CALLBACK_HMAC_KEY, ctx.callbackQuery.data);
    if (!v || v.kind !== CB_KIND) return next();
    try {
      await route(ctx, v.payload);
    } catch (e) {
      console.error("funnel callback failed", v.payload, String(e));
      await ctx.answerCallbackQuery({ text: "Something went wrong — send /start to try again." }).catch(() => {});
    }
  });
}

async function route(ctx: Ctx, payload: string) {
  const [step, a, b] = payload.split(":");
  await ctx.answerCallbackQuery().catch(() => {});
  switch (step) {
    case "start": return start(ctx);
    case "enter": return enter(ctx);
    case "attest": return attest(ctx);
    case "tier": return pickRail(ctx, a ?? "");
    case "rail": return chooseRail(ctx, a as Rail, b ?? "");
    default: return start(ctx);
  }
}

// ── steps ──────────────────────────────────────────────────────────────────

async function start(ctx: Ctx) {
  const uid = ctx.from!.id;
  const snap = await memberStub(ctx.env, uid).snapshot(uid);
  if (isActive(snap.state)) return ctx.reply(statusText(ctx.cfg, snap), { parse_mode: "HTML" });
  if (snap.state === "banned") return ctx.reply("This account can't join the community.");
  const kb = new InlineKeyboard().text("Enter →", await cb(ctx.env, "enter"));
  await ctx.reply(pitchText(ctx.cfg), { parse_mode: "HTML", reply_markup: kb });
}

async function enter(ctx: Ctx) {
  const uid = ctx.from!.id;
  const snap = await memberStub(ctx.env, uid).snapshot(uid);
  if (isActive(snap.state)) return ctx.reply(statusText(ctx.cfg, snap), { parse_mode: "HTML" });
  if (snap.state === "banned") return ctx.reply("This account can't join the community.");
  if (await hasAttested(ctx.env, uid, ctx.cfg.attestationVersion)) {
    await memberStub(ctx.env, uid).tryApply(uid, { type: "attest" }, "funnel", "attest_cached");
    return pickTier(ctx);
  }
  const kb = new InlineKeyboard().text(ATTEST_BUTTON, await cb(ctx.env, "attest"));
  await ctx.reply(ATTESTATION_TEXT, { reply_markup: kb });
}

async function attest(ctx: Ctx) {
  const uid = ctx.from!.id;
  const v = ctx.cfg.attestationVersion;
  if (!(await hasAttested(ctx.env, uid, v))) {
    await ctx.env.DB.prepare("INSERT INTO attestations (user_id, policy_version, attested_at, lang) VALUES (?, ?, ?, ?)")
      .bind(uid, v, nowIso(), ctx.from?.language_code ?? null).run();
  }
  const r = await memberStub(ctx.env, uid).tryApply(uid, { type: "attest" }, "funnel");
  if (!r) {
    const snap = await memberStub(ctx.env, uid).snapshot(uid);
    if (isActive(snap.state)) return ctx.reply(statusText(ctx.cfg, snap), { parse_mode: "HTML" });
    return ctx.reply("This account can't join the community.");
  }
  await pickTier(ctx);
}

async function pickTier(ctx: Ctx) {
  const kb = new InlineKeyboard();
  for (const t of ctx.cfg.tiers) kb.text(`${t.emoji} ${t.name} · ⭐${t.stars} / $${t.usd.toFixed(2)}`, await cb(ctx.env, `tier:${t.code}`)).row();
  const legend = ctx.cfg.tiers.map((t) => `${t.emoji} <b>${esc(t.name)}</b> — ${tierAccessLabel(t, ctx.cfg)}`).join("\n");
  await ctx.reply(`<b>Choose your tier.</b>\n${legend}\n\nEvery tier is 30 days, renews monthly, and you can leave any time.`, { parse_mode: "HTML", reply_markup: kb });
}

async function pickRail(ctx: Ctx, code: string) {
  const tier = tierByCode(ctx.cfg, code);
  if (!tier) return pickTier(ctx);
  const kb = new InlineKeyboard()
    .text("⭐ Stars – renews automatically", await cb(ctx.env, `rail:stars:${tier.code}`)).row()
    .text("💳 Card / Crypto", await cb(ctx.env, `rail:external:${tier.code}`));
  await ctx.reply(
    `${tier.emoji} <b>${esc(tier.name)}</b> — ⭐${tier.stars} or $${tier.usd.toFixed(2)} per 30 days.\n\nHow would you like to pay?`,
    { parse_mode: "HTML", reply_markup: kb },
  );
}

async function chooseRail(ctx: Ctx, rail: Rail, code: string) {
  const uid = ctx.from!.id;
  const tier = tierByCode(ctx.cfg, code);
  if (!tier || (rail !== "stars" && rail !== "external")) return pickTier(ctx);
  const stub = memberStub(ctx.env, uid);
  const r = await stub.tryApply(uid, { type: "choose_rail", rail, tier: tier.code }, "funnel");
  if (!r) {
    const snap = await stub.snapshot(uid);
    if (isActive(snap.state)) return ctx.reply(statusText(ctx.cfg, snap), { parse_mode: "HTML" });
    return ctx.reply("Let's start from the top — send /start.");
  }
  if (!(await setupReady(ctx.env, ctx.api, ctx.cfg))) {
    return ctx.reply("The creator hasn't finished setting up the rooms yet. Try again a little later — your progress is saved. 🌸");
  }
  if (rail === "stars") {
    const link = await starsSubscriptionLink(ctx.api, ctx.cfg.channelChatId, `u${uid} ${tier.code}`, tier.stars);
    await ctx.env.DB.prepare("UPDATE memberships SET stars_invite_link = ? WHERE user_id = ?").bind(link, uid).run();
    await storeLink(ctx.env, link, uid, "channel", new Date(Date.now() + 365 * 86400_000).toISOString());
    await ctx.reply(
      [
        `${tier.emoji} <b>${esc(tier.name)} via Telegram Stars</b>`,
        "",
        `Tap the link, confirm ⭐${tier.stars}, and Telegram bills you every ${STARS_PERIOD_DAYS} days automatically. Cancel any time from Telegram Settings → My Stars.`,
        "",
        link,
        "",
        "The moment you're in the feed, I'll DM you the link to the room. 🌹",
      ].join("\n"),
      { parse_mode: "HTML", link_preview_options: { is_disabled: true } },
    );
  } else {
    const url = await PROCESSORS.fake!.checkoutUrl(ctx.env, uid, tier.code);
    await ctx.reply(
      [
        `${tier.emoji} <b>${esc(tier.name)} via card or crypto</b> — $${tier.usd.toFixed(2)} / ${STARS_PERIOD_DAYS} days.`,
        "",
        "Complete checkout here:",
        url,
        "",
        "As soon as the payment confirms, I'll DM you your links. 🌹",
      ].join("\n"),
      { parse_mode: "HTML", link_preview_options: { is_disabled: true } },
    );
  }
}

// ── helpers ────────────────────────────────────────────────────────────────

export function parseRef(match: string | undefined): number | null {
  const m = /^ref_(\d{1,20})$/.exec((match ?? "").trim());
  return m ? Number(m[1]) : null;
}

async function recordReferrer(env: Env, from: { id: number; username?: string; first_name: string }, referrerId: number) {
  await upsertMember(env, from, referrerId);
  await env.DB.prepare("UPDATE members SET referrer_id = ? WHERE user_id = ? AND referrer_id IS NULL AND ? != user_id")
    .bind(referrerId, from.id, referrerId).run();
}

async function hasAttested(env: Env, userId: number, version: number): Promise<boolean> {
  const r = await env.DB.prepare("SELECT 1 FROM attestations WHERE user_id = ? AND policy_version = ? LIMIT 1").bind(userId, version).first();
  return !!r;
}

export function pitchText(cfg: Config): string {
  const cheapest = [...cfg.tiers].sort((a, b) => a.stars - b.stars)[0];
  return [
    `🌹 <b>${esc(cfg.communityName)}</b>`,
    "",
    `A private room with ${esc(cfg.creatorName)}: exclusive posts in the feed, a members-only chat, daily ${esc(cfg.pointsName)} ${cfg.pointsEmoji}, games, and a shop where your ${esc(cfg.pointsName)} buy real perks.`,
    "",
    "• Pay with Telegram Stars or card/crypto",
    "• 30-day membership, renews monthly, cancel any time",
    cheapest ? `• From ⭐${cheapest.stars} / $${cheapest.usd.toFixed(2)}` : "",
    "",
    "18+ only. Tap Enter to continue.",
  ].filter((l) => l !== undefined).join("\n");
}

export function statusText(cfg: Config, snap: MemberSnapshot): string {
  const tier = tierByCode(cfg, snap.tier);
  const end = snap.periodEndAt ? snap.periodEndAt.slice(0, 10) : "—";
  const lines = [
    `${tier?.emoji ?? "🌸"} <b>You're a member of ${esc(cfg.communityName)}.</b>`,
    `Tier: <b>${esc(tier?.name ?? snap.tier ?? "—")}</b>`,
    snap.state === "grace"
      ? `⚠️ Your period ended ${end}. Renew before ${snap.graceUntil?.slice(0, 10) ?? "soon"} to keep your access.`
      : `Current period ends: <b>${end}</b>`,
    "",
    snap.rail === "stars"
      ? "Manage: Telegram Settings → My Stars → Subscriptions."
      : "Manage: the receipt e-mail from checkout has your subscription controls.",
  ];
  return lines.join("\n");
}
