import { env } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { loadConfig, setConfig } from "../src/config";
import { memberStub } from "../src/do/MemberDO";
import type { Env } from "../src/env";
import { adminBan, adminKick, adminRefundStars, adminUnban, listMembers } from "../src/handlers/membership/admin";
import { handlePaymentEvent } from "../src/handlers/membership/payments";
import { reconcileMemberships } from "../src/handlers/membership/reconcile";
import { getPoints, getXp } from "../src/services/ledger";
import type { PaymentEvent } from "../src/services/payments/types";
import { CHANNEL, chatMemberUpdate, GROUP, joinRequestUpdate, makeBot } from "./tg-harness";

const E = env as unknown as Env;
const exec = { waitUntil() {} } as unknown as ExecutionContext;
const future = (days: number) => new Date(Date.now() + days * 86400_000).toISOString();

function evt(userId: number, kind: PaymentEvent["kind"], eventId: string, extra: Partial<PaymentEvent> = {}): PaymentEvent {
  return { processor: "fake", eventId, kind, userId, tier: "vip", amount: 999, currency: "USD", periodEndAt: future(30), occurredAt: new Date().toISOString(), raw: { eventId }, ...extra };
}

describe("membership flow", () => {
  beforeEach(async () => {
    await setConfig(E, "groupChatId", GROUP);
    await setConfig(E, "channelChatId", CHANNEL);
  });

  it("VIP (feed-only) gets just the channel link and is refused at the group", async () => {
    const { bot, rec } = await makeBot();
    const uid = 600;
    await handlePaymentEvent(E, exec, evt(uid, "initial", "e0"), bot.api);
    const links = await E.DB.prepare("SELECT chat_kind FROM invite_links WHERE user_id = ?").bind(uid).all<{ chat_kind: string }>();
    expect(links.results.map((l) => l.chat_kind)).toEqual(["channel"]);
    await bot.handleUpdate(joinRequestUpdate(uid, GROUP, { invite_link: "https://t.me/+forged" }, "qid-0"));
    expect(rec.last("answerChatJoinRequestQuery")).toMatchObject({ chat_join_request_query_id: "qid-0", result: "decline" });
  });

  it("external payment activates, reveals both links, and is idempotent", async () => {
    const { bot, rec } = await makeBot();
    const uid = 601;
    const r1 = await handlePaymentEvent(E, exec, evt(uid, "initial", "e1", { subscriptionId: "sub_1", tier: "vipplus" }), bot.api);
    expect(r1).toEqual({ ok: true, note: "none -> active" });
    const snap = await memberStub(E, uid).snapshot(uid);
    expect(snap).toMatchObject({ state: "active", rail: "external", tier: "vipplus" });
    const links = await E.DB.prepare("SELECT chat_kind FROM invite_links WHERE user_id = ? ORDER BY chat_kind").bind(uid).all<{ chat_kind: string }>();
    expect(links.results.map((l) => l.chat_kind)).toEqual(["channel", "group"]);
    const ms = await E.DB.prepare("SELECT external_subscription_id FROM memberships WHERE user_id = ?").bind(uid).first<{ external_subscription_id: string }>();
    expect(ms?.external_subscription_id).toBe("sub_1");

    expect(await handlePaymentEvent(E, exec, evt(uid, "initial", "e1"), bot.api)).toEqual({ ok: true, note: "duplicate" });
    const pays = await E.DB.prepare("SELECT count(*) AS n FROM payments WHERE user_id = ?").bind(uid).first<{ n: number }>();
    expect(pays?.n).toBe(1);

    // join request on own group link → approved via query id, link consumed, presence tracked
    const group = await E.DB.prepare("SELECT link FROM invite_links WHERE user_id = ? AND chat_kind = 'group'").bind(uid).first<{ link: string }>();
    await bot.handleUpdate(joinRequestUpdate(uid, GROUP, { invite_link: group!.link }, "qid-1"));
    expect(rec.last("answerChatJoinRequestQuery")).toMatchObject({ chat_join_request_query_id: "qid-1", result: "approve" });
    const used = await E.DB.prepare("SELECT used_by FROM invite_links WHERE link = ?").bind(group!.link).first<{ used_by: number }>();
    expect(used?.used_by).toBe(uid);
    const pres = await E.DB.prepare("SELECT in_group FROM memberships WHERE user_id = ?").bind(uid).first<{ in_group: number }>();
    expect(pres?.in_group).toBe(1);

    // someone else using that (consumed) link → declined, audited, told to /start
    rec.reset();
    await bot.handleUpdate(joinRequestUpdate(602, GROUP, { invite_link: group!.link }));
    expect(rec.last("declineChatJoinRequest")).toMatchObject({ chat_id: GROUP, user_id: 602 });
    expect(String(rec.last("sendMessage")!.text)).toContain("/start");
    const audit = await E.DB.prepare("SELECT actor_id, target FROM audit_log WHERE action = 'link_shared'").first<{ actor_id: number; target: string }>();
    expect(audit).toEqual({ actor_id: 602, target: String(uid) });

    // rebill while active → renewal reward, no new links
    rec.reset();
    const end60 = future(60);
    const r2 = await handlePaymentEvent(E, exec, evt(uid, "rebill", "e2", { periodEndAt: end60 }), bot.api);
    expect(r2.note).toBe("active -> active");
    expect(rec.of("createChatInviteLink")).toHaveLength(0);
    expect(await getPoints(E, uid)).toBe(100);
    expect((await getXp(E, uid)).xp).toBe(200);
    await handlePaymentEvent(E, exec, evt(uid, "rebill", "e3", { periodEndAt: end60 }), bot.api); // same period end → same ref → no double reward
    expect(await getPoints(E, uid)).toBe(100);

    // chargeback → banned, banned in both chats
    rec.reset();
    const r3 = await handlePaymentEvent(E, exec, evt(uid, "chargeback", "e4"), bot.api);
    expect(r3.note).toBe("active -> banned");
    expect(rec.of("banChatMember").map((c) => c.payload.chat_id).sort()).toEqual([CHANNEL, GROUP].sort());
  });

  it("welcome ritual fires once on first group join", async () => {
    const { bot, rec } = await makeBot();
    const uid = 611;
    await bot.handleUpdate(chatMemberUpdate(uid, GROUP, "left", "member"));
    expect(await getPoints(E, uid)).toBe(20);
    const say = rec.of("sendMessage").find((c) => c.payload.chat_id === GROUP && !c.payload.receiver_user_id)!;
    expect(String(say.payload.text)).toContain("A new petal falls");
    expect(say.payload.message_effect_id).toBe("5046509860389126442");
    expect(rec.of("sendMessage").some((c) => c.payload.receiver_user_id === uid && String(c.payload.text).includes("/claim"))).toBe(true);
    rec.reset();
    await bot.handleUpdate(chatMemberUpdate(uid, GROUP, "left", "member"));
    expect(rec.of("sendMessage")).toHaveLength(0);
    expect(await getPoints(E, uid)).toBe(20);
  });

  it("Stars: channel join via subscription link activates; leaving ends the period", async () => {
    const { bot, rec } = await makeBot();
    const uid = 621;
    await memberStub(E, uid).apply(uid, { type: "attest" }, "test");
    await memberStub(E, uid).apply(uid, { type: "choose_rail", rail: "stars", tier: "vipplus" }, "test");
    await bot.handleUpdate(chatMemberUpdate(uid, CHANNEL, "left", "member", { invite_link: "https://t.me/+subX", subscription_price: 1500 }));
    const snap = await memberStub(E, uid).snapshot(uid);
    expect(snap).toMatchObject({ state: "active", rail: "stars", tier: "vipplus" });
    expect(Date.parse(snap.periodEndAt!)).toBeGreaterThan(Date.now() + 29 * 86400_000);
    const pay = await E.DB.prepare("SELECT kind, amount, external_event_id FROM payments WHERE user_id = ?").bind(uid).first<{ kind: string; amount: number; external_event_id: string }>();
    expect(pay).toMatchObject({ kind: "stars_sub", amount: 1500 });
    expect(pay!.external_event_id).toMatch(new RegExp(`^tgsub:${uid}:\\d{4}-\\d{2}-\\d{2}$`));
    // grant_access for Stars rail = group link only
    expect(rec.of("createChatInviteLink").map((c) => c.payload.chat_id)).toEqual([GROUP]);
    expect((await E.DB.prepare("SELECT in_channel FROM memberships WHERE user_id = ?").bind(uid).first<{ in_channel: number }>())!.in_channel).toBe(1);

    // replayed update → nothing new
    rec.reset();
    await bot.handleUpdate(chatMemberUpdate(uid, CHANNEL, "left", "member", { invite_link: "https://t.me/+subX", subscription_price: 1500 }));
    expect(rec.of("createChatInviteLink")).toHaveLength(0);

    // Telegram removes them → period_end_at pulled to now; reconcile puts them in grace + reminder DM
    await bot.handleUpdate(chatMemberUpdate(uid, CHANNEL, "member", "left"));
    rec.reset();
    await reconcileMemberships(E, exec, await loadConfig(E), bot.api);
    const g = await memberStub(E, uid).snapshot(uid);
    expect(g.state).toBe("grace");
    expect(rec.of("sendMessage").filter((c) => c.payload.chat_id === uid).map((c) => String(c.payload.text)).join()).toContain("period has ended");
    rec.reset();
    await reconcileMemberships(E, exec, await loadConfig(E), bot.api);
    expect(rec.of("sendMessage")).toHaveLength(0); // no repeat reminder
  });

  it("Stars: still-subscribed at period end renews instead of lapsing", async () => {
    const { bot, rec } = await makeBot();
    const uid = 631;
    await memberStub(E, uid).apply(uid, { type: "payment_ok", rail: "stars", tier: "vip", periodEndAt: new Date(Date.now() - 60_000).toISOString() }, "test");
    rec.results.getChatMember = (p) => ({ status: "member", user: { id: p.user_id, is_bot: false, first_name: "x" } });
    await reconcileMemberships(E, exec, await loadConfig(E), bot.api);
    const s = await memberStub(E, uid).snapshot(uid);
    expect(s.state).toBe("active");
    expect(Date.parse(s.periodEndAt!)).toBeGreaterThan(Date.now() + 29 * 86400_000);
    expect(await getPoints(E, uid)).toBe(100);
  });

  it("grace expiry kicks via TG_OPS and sends a win-back DM", async () => {
    const { bot, rec } = await makeBot();
    const uid = 641;
    await memberStub(E, uid).apply(uid, { type: "payment_ok", rail: "external", tier: "vip", periodEndAt: future(30) }, "test");
    await memberStub(E, uid).apply(uid, { type: "period_ended", graceUntil: new Date(Date.now() - 1000).toISOString() }, "test");
    await reconcileMemberships(E, exec, await loadConfig(E), bot.api);
    expect((await memberStub(E, uid).snapshot(uid)).state).toBe("lapsed");
    const wb = rec.of("sendMessage").find((c) => c.payload.chat_id === uid && String(c.payload.text).includes("isn't locked"));
    expect(wb).toBeTruthy();
    expect((wb!.payload.reply_markup as { inline_keyboard: { callback_data: string }[][] }).inline_keyboard[0]![0]!.callback_data).toMatch(/^fn:start:/);
  });

  it("admin helpers: ban, unban, kick, refund limitation, list", async () => {
    const { bot, rec } = await makeBot();
    const cfg = await loadConfig(E);
    const uid = 651;
    await memberStub(E, uid).apply(uid, { type: "payment_ok", rail: "external", tier: "vip", periodEndAt: future(30) }, "test");
    expect((await listMembers(E, "active")).map((m) => m.user_id)).toContain(uid);

    const b = await adminBan(E, bot.api, cfg, 1, uid, "spam");
    expect(b.ok && b.snapshot?.state).toBe("banned");
    expect(rec.of("banChatMember")).toHaveLength(2);
    expect((await listMembers(E, "active")).map((m) => m.user_id)).not.toContain(uid);

    const u = await adminUnban(E, bot.api, cfg, 1, uid);
    expect(u.ok && u.snapshot?.state).toBe("lapsed");
    expect(rec.of("unbanChatMember")).toHaveLength(2);
    expect(await adminUnban(E, bot.api, cfg, 1, uid)).toMatchObject({ ok: false });

    await memberStub(E, uid).apply(uid, { type: "payment_ok", rail: "external", tier: "vip", periodEndAt: future(30) }, "test");
    const k = await adminKick(E, bot.api, cfg, 1, uid, "rules");
    expect(k.snapshot?.state).toBe("lapsed");
    const audits = await E.DB.prepare("SELECT action FROM audit_log WHERE target = ? ORDER BY id").bind(String(uid)).all<{ action: string }>();
    expect(audits.results.map((a) => a.action)).toEqual(["admin_ban", "admin_unban", "admin_kick"]);

    expect(await adminRefundStars(E, bot.api, cfg, 1, uid)).toMatchObject({ ok: false });
    await E.DB.prepare("INSERT INTO payments (user_id, rail, external_event_id, external_txn_id, kind, amount, currency, occurred_at) VALUES (?, 'stars', 'tip:1', 'chg_1', 'stars_tip', 50, 'XTR', ?)").bind(uid, new Date().toISOString()).run();
    const r = await adminRefundStars(E, bot.api, cfg, 1, uid);
    expect(r.ok).toBe(true);
    expect(rec.last("refundStarPayment")).toMatchObject({ user_id: uid, telegram_payment_charge_id: "chg_1" });
  });
});

import { adminComp } from "../src/handlers/membership/admin";

describe("comp", () => {
  it("activates a free membership, is idempotent per day, and refuses banned users", async () => {
    const { bot } = await makeBot();
    const uid = 777;
    const r = await adminComp(E, bot.api, await loadConfig(E), 1, uid, "vipplus", 14);
    expect(r.ok).toBe(true);
    expect(r.snapshot).toMatchObject({ state: "active", rail: "external", tier: "vipplus" });
    const again = await adminComp(E, bot.api, await loadConfig(E), 1, uid, "vipplus", 14);
    expect(again.ok).toBe(true);
    const pays = await E.DB.prepare("SELECT count(*) AS n FROM payments WHERE user_id = ?").bind(uid).first<{ n: number }>();
    expect(pays?.n).toBe(1);
    expect((await adminComp(E, bot.api, await loadConfig(E), 1, uid, "gold")).ok).toBe(false);
    await memberStub(E, uid).apply(uid, { type: "ban" }, "test");
    expect((await adminComp(E, bot.api, await loadConfig(E), 1, uid, "vip")).note).toContain("banned");
  });
});
