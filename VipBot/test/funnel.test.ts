import { env } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { setConfig } from "../src/config";
import { verifyCb } from "../src/domain/callbacks";
import { memberStub } from "../src/do/MemberDO";
import type { Env } from "../src/env";
import { ATTESTATION_TEXT, ATTEST_BUTTON, parseRef } from "../src/handlers/funnel";
import { buttons, cbUpdate, CHANNEL, dmUpdate, GROUP, makeBot } from "./tg-harness";

const E = env as unknown as Env;

describe("funnel", () => {
  beforeEach(async () => {
    await setConfig(E, "groupChatId", GROUP);
    await setConfig(E, "channelChatId", CHANNEL);
  });

  it("parses referral payloads", () => {
    expect(parseRef("ref_123")).toBe(123);
    expect(parseRef("")).toBeNull();
    expect(parseRef("ref_abc")).toBeNull();
  });

  it("walks /start → attest → tier → Stars rail", async () => {
    const { bot, rec } = await makeBot();
    const uid = 501;

    await bot.handleUpdate(dmUpdate(uid, "/start ref_999"));
    const pitch = rec.last("sendMessage")!;
    expect(String(pitch.text)).toContain("Enter");
    const [enter] = buttons(pitch);
    expect(enter!.text).toBe("Enter →");
    expect(await verifyCb(E.CALLBACK_HMAC_KEY, enter!.data)).toEqual({ kind: "fn", payload: "enter" });
    const m = await E.DB.prepare("SELECT referrer_id FROM members WHERE user_id = ?").bind(uid).first<{ referrer_id: number }>();
    expect(m?.referrer_id).toBe(999);

    await bot.handleUpdate(cbUpdate(uid, enter!.data));
    const att = rec.last("sendMessage")!;
    expect(att.text).toBe(ATTESTATION_TEXT);
    const [confirm] = buttons(att);
    expect(confirm!.text).toBe(ATTEST_BUTTON);

    await bot.handleUpdate(cbUpdate(uid, confirm!.data));
    const a = await E.DB.prepare("SELECT policy_version FROM attestations WHERE user_id = ?").bind(uid).first<{ policy_version: number }>();
    expect(a?.policy_version).toBe(1);
    expect((await memberStub(E, uid).snapshot(uid)).state).toBe("attested");
    const tiers = buttons(rec.last("sendMessage"));
    expect(tiers.map((b) => b.text)).toEqual(["🌸 VIP · ⭐500 / $9.99", "🌹 VIP+ · ⭐1500 / $24.99"]);

    await bot.handleUpdate(cbUpdate(uid, tiers[1]!.data));
    const rails = buttons(rec.last("sendMessage"));
    expect(rails.map((b) => b.text)).toEqual(["⭐ Stars – renews automatically", "💳 Card / Crypto"]);

    await bot.handleUpdate(cbUpdate(uid, rails[0]!.data));
    const snap = await memberStub(E, uid).snapshot(uid);
    expect(snap).toMatchObject({ state: "pending_payment", rail: "stars", tier: "vipplus" });
    const sub = rec.last("createChatSubscriptionInviteLink")!;
    expect(sub).toMatchObject({ chat_id: CHANNEL, subscription_price: 1500, subscription_period: 2592000 });
    const row = await E.DB.prepare("SELECT stars_invite_link FROM memberships WHERE user_id = ?").bind(uid).first<{ stars_invite_link: string }>();
    expect(row?.stars_invite_link).toMatch(/^https:\/\/t\.me\/\+sub/);
    const link = await E.DB.prepare("SELECT chat_kind, user_id FROM invite_links WHERE link = ?").bind(row!.stars_invite_link).first();
    expect(link).toMatchObject({ chat_kind: "channel", user_id: uid });
    expect(String(rec.last("sendMessage")!.text)).toContain(row!.stars_invite_link);
  });

  it("external rail hands out a checkout URL", async () => {
    const { bot, rec } = await makeBot();
    const uid = 502;
    await bot.handleUpdate(dmUpdate(uid, "/start"));
    await bot.handleUpdate(cbUpdate(uid, buttons(rec.last("sendMessage"))[0]!.data));
    await bot.handleUpdate(cbUpdate(uid, buttons(rec.last("sendMessage"))[0]!.data));
    await bot.handleUpdate(cbUpdate(uid, buttons(rec.last("sendMessage"))[0]!.data)); // VIP
    await bot.handleUpdate(cbUpdate(uid, buttons(rec.last("sendMessage"))[1]!.data)); // card
    expect(await memberStub(E, uid).snapshot(uid)).toMatchObject({ state: "pending_payment", rail: "external", tier: "vip" });
    expect(String(rec.last("sendMessage")!.text)).toContain(`https://example.invalid/checkout?user=${uid}&tier=vip`);
  });

  it("skips the attestation when the current version is already on file, re-prompts after a bump", async () => {
    const { bot, rec } = await makeBot();
    const uid = 503;
    await E.DB.prepare("INSERT INTO attestations (user_id, policy_version, attested_at) VALUES (?, 1, ?)").bind(uid, new Date().toISOString()).run();
    await bot.handleUpdate(dmUpdate(uid, "/start"));
    await bot.handleUpdate(cbUpdate(uid, buttons(rec.last("sendMessage"))[0]!.data));
    expect(String(rec.last("sendMessage")!.text)).toContain("Choose your tier");
    expect((await memberStub(E, uid).snapshot(uid)).state).toBe("attested");

    await setConfig(E, "attestationVersion", 2);
    const fresh = await makeBot();
    await fresh.bot.handleUpdate(dmUpdate(uid, "/start"));
    await fresh.bot.handleUpdate(cbUpdate(uid, buttons(fresh.rec.last("sendMessage"))[0]!.data));
    expect(fresh.rec.last("sendMessage")!.text).toBe(ATTESTATION_TEXT);
  });

  it("shows status for active members and refuses banned ones; ignores self-referral", async () => {
    const { bot, rec } = await makeBot();
    const uid = 504;
    await memberStub(E, uid).apply(uid, { type: "payment_ok", rail: "stars", tier: "vip", periodEndAt: "2030-01-01T00:00:00.000Z" }, "test");
    await bot.handleUpdate(dmUpdate(uid, `/start ref_${uid}`));
    const t = String(rec.last("sendMessage")!.text);
    expect(t).toContain("You're a member");
    expect(t).toContain("VIP");
    expect(t).toContain("2030-01-01");
    expect(t).toContain("Manage");
    const m = await E.DB.prepare("SELECT referrer_id FROM members WHERE user_id = ?").bind(uid).first<{ referrer_id: number | null }>();
    expect(m?.referrer_id).toBeNull();

    await memberStub(E, uid).apply(uid, { type: "ban" }, "test");
    await bot.handleUpdate(dmUpdate(uid, "/start"));
    expect(String(rec.last("sendMessage")!.text)).toContain("can't join");
  });

  it("tells the user (and nags admins once) when chats are not configured", async () => {
    await setConfig(E, "groupChatId", 0);
    const { bot, rec } = await makeBot();
    const uid = 505;
    await bot.handleUpdate(dmUpdate(uid, "/start"));
    await bot.handleUpdate(cbUpdate(uid, buttons(rec.last("sendMessage"))[0]!.data));
    await bot.handleUpdate(cbUpdate(uid, buttons(rec.last("sendMessage"))[0]!.data));
    await bot.handleUpdate(cbUpdate(uid, buttons(rec.last("sendMessage"))[0]!.data)); // VIP
    rec.reset();
    await bot.handleUpdate(cbUpdate(uid, await signed("rail:stars:vip")));
    const sends = rec.of("sendMessage").map((c) => c.payload);
    expect(sends.some((p) => p.chat_id === 1 && String(p.text).includes("group chat isn't configured"))).toBe(true);
    expect(sends.some((p) => p.chat_id === uid && String(p.text).includes("hasn't finished setting up"))).toBe(true);
    expect(rec.of("createChatSubscriptionInviteLink")).toHaveLength(0);
  });
});

async function signed(payload: string) {
  const { signCb } = await import("../src/domain/callbacks");
  return signCb(E.CALLBACK_HMAC_KEY, "fn", payload);
}
