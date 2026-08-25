import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import {
  applyPendingTitle, discountedPrice, fulfillOrder, itemByCode, purchase, refundOrder, refundStaleOrders, seedDefaultItems, type Purchase,
} from "../src/handlers/shop/core";
import { parseShopAdd } from "../src/handlers/shop/index";
import { fakeApi } from "./fakeApi";
import { balance, seedMember, testCfg } from "./games-shop-helpers";

const cfg = testCfg();

describe("shop", () => {
  it("seeds defaults once", async () => {
    expect(await seedDefaultItems(env)).toBe(true);
    expect(await seedDefaultItems(env)).toBe(false);
    const n = await env.DB.prepare("SELECT COUNT(*) AS n FROM shop_items").first<{ n: number }>();
    expect(n?.n).toBe(9);
    expect((await itemByCode(env, "dmslot"))?.min_tier).toBe("vipplus");
  });

  it("auto items: charges once per ref, applies discount, fulfills by code", async () => {
    await seedDefaultItems(env);
    const { api, of } = fakeApi();
    await seedMember(10, { balance: 500, level: 6 });
    const saver = (await itemByCode(env, "saver"))!;
    const r1 = await purchase(env, cfg, api, { id: 10, first_name: "Ten" }, saver.id, "cq-1");
    expect(r1.ok).toBe(true);
    if (!r1.ok) return;
    expect(r1.price).toBe(discountedPrice(60, 6)); // 57
    expect(r1.purchase.status).toBe("fulfilled");
    expect(await balance(10)).toBe(500 - 57);
    const dup = await purchase(env, cfg, api, { id: 10, first_name: "Ten" }, saver.id, "cq-1");
    expect(dup.ok).toBe(false);
    expect(!dup.ok && dup.reason).toBe("duplicate");
    expect(await balance(10)).toBe(500 - 57);
    const st = await env.DB.prepare("SELECT savers FROM streaks WHERE user_id = 10").first<{ savers: number }>();
    expect(st?.savers).toBe(1);

    const shout = (await itemByCode(env, "shoutout"))!;
    const r2 = await purchase(env, cfg, api, { id: 10, first_name: "Ten" }, shout.id, "cq-2");
    expect(r2.ok).toBe(true);
    expect(of("sendMessage").some((c) => c.args[0] === cfg.groupChatId && String(c.args[1]).includes("Shoutout"))).toBe(true);

    const vote = (await itemByCode(env, "vote2x"))!;
    expect((await purchase(env, cfg, api, { id: 10, first_name: "Ten" }, vote.id, "cq-3")).ok).toBe(true);
    expect(await env.KV.get("vote2x:10")).toBeTruthy();
  });

  it("title7d asks for text via DM and applies it", async () => {
    await seedDefaultItems(env);
    const { api, of } = fakeApi();
    await seedMember(11, { balance: 1000 });
    const item = (await itemByCode(env, "title7d"))!;
    const r = await purchase(env, cfg, api, { id: 11, first_name: "E" }, item.id, "cq-t1");
    expect(r.ok).toBe(true);
    expect(await env.KV.get("pending_title:11")).toBeTruthy();
    expect(of("sendMessage").some((c) => c.args[0] === 11)).toBe(true);
    expect(await applyPendingTitle(env, cfg, api, 11, "this title is way too long")).toMatch(/16 characters/);
    expect(await applyPendingTitle(env, cfg, api, 11, "Night Owl")).toMatch(/Night Owl/);
    expect(of("promoteChatMember")).toHaveLength(1);
    expect(of("setChatAdministratorCustomTitle")[0]?.args).toEqual([cfg.groupChatId, 11, "Night Owl"]);
    expect(await env.KV.get("pending_title:11")).toBeNull();
    expect(await applyPendingTitle(env, cfg, api, 11, "again")).toBeNull();
  });

  it("gates on membership, tier, balance", async () => {
    await seedDefaultItems(env);
    const { api } = fakeApi();
    const dm = (await itemByCode(env, "dmslot"))!;
    await seedMember(12, { balance: 5000, tier: "vip" });
    expect((await purchase(env, cfg, api, { id: 12, first_name: "x" }, dm.id, "cq-g1")) as { reason?: string }).toMatchObject({ ok: false, reason: "tier" });
    await seedMember(13, { balance: 10, tier: "vipplus" });
    expect((await purchase(env, cfg, api, { id: 13, first_name: "x" }, dm.id, "cq-g2")) as { reason?: string }).toMatchObject({ ok: false, reason: "insufficient" });
    expect(await balance(13)).toBe(10);
    await seedMember(14, { balance: 5000, state: "lapsed" });
    expect((await purchase(env, cfg, api, { id: 14, first_name: "x" }, dm.id, "cq-g3")) as { reason?: string }).toMatchObject({ ok: false, reason: "not_member" });
  });

  it("queued orders: admin DM, fulfill, refund (idempotent), stale sweep", async () => {
    await seedDefaultItems(env);
    const { api, of } = fakeApi();
    await seedMember(15, { balance: 1000 });
    const post = (await itemByCode(env, "postcredit"))!; // 400, refund_after_days 14
    const r = await purchase(env, cfg, api, { id: 15, first_name: "F", username: "fifteen" }, post.id, "cq-q1");
    expect(r.ok && r.purchase.status).toBe("queued");
    expect(of("sendMessage").some((c) => c.args[0] === 1 && String(c.args[1]).includes("@fifteen"))).toBe(true); // admin id 1
    const id = r.ok ? r.purchase.id : 0;

    expect(await refundOrder(env, api, 1, id)).toMatch(/refunded/);
    expect(await balance(15)).toBe(1000);
    expect(await refundOrder(env, api, 1, id)).toMatch(/already/);
    expect(await balance(15)).toBe(1000);
    expect(await fulfillOrder(env, api, 1, id)).toMatch(/already refunded/);

    const r2 = await purchase(env, cfg, api, { id: 15, first_name: "F" }, post.id, "cq-q2");
    const id2 = r2.ok ? r2.purchase.id : 0;
    expect(await fulfillOrder(env, api, 1, id2, "posted Friday")).toMatch(/fulfilled/);
    const p = await env.DB.prepare("SELECT * FROM purchases WHERE id = ?").bind(id2).first<Purchase>();
    expect(p?.note).toBe("posted Friday");
    expect(p?.fulfilled_by).toBe(1);

    // stale: backdate a queued order past 14 days
    const r3 = await purchase(env, cfg, api, { id: 15, first_name: "F" }, post.id, "cq-q3");
    const id3 = r3.ok ? r3.purchase.id : 0;
    const before = await balance(15);
    expect(await refundStaleOrders(env, api)).toBe(0);
    await env.DB.prepare("UPDATE purchases SET created_at = ? WHERE id = ?").bind("2020-01-01T00:00:00.000Z", id3).run();
    expect(await refundStaleOrders(env, api)).toBe(1);
    expect(await balance(15)).toBe(before + 400);
    // items without refund_after_days are never auto-refunded
    const ama = (await itemByCode(env, "ama"))!;
    const r4 = await purchase(env, cfg, api, { id: 15, first_name: "F" }, ama.id, "cq-q4");
    await env.DB.prepare("UPDATE purchases SET created_at = ? WHERE id = ?").bind("2020-01-01T00:00:00.000Z", r4.ok ? r4.purchase.id : 0).run();
    expect(await refundStaleOrders(env, api)).toBe(0);
  });

  it("parses /shop add", () => {
    expect(parseShopAdd('poster "Signed poster" 900 queue vipplus Ships worldwide')).toEqual({ code: "poster", name: "Signed poster", price: 900, fulfillment: "queue", minTier: "vipplus", desc: "Ships worldwide" });
    expect(parseShopAdd('x "Y" 5 auto')).toMatchObject({ code: "x", minTier: null, desc: null });
    expect(parseShopAdd("bad")).toBeNull();
  });
});
