import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { claimDrop, settleDrop, spawnDrop, DROP_TEXT, MAX_SAVERS } from "../src/handlers/games/drops";
import { fakeApi } from "./fakeApi";
import { balance, seedMember, testCfg } from "./games-shop-helpers";

describe("drop claims", () => {
  it("concurrent taps yield exactly one winner", async () => {
    const { api, of } = fakeApi();
    const dropId = await spawnDrop(env, api, -1001, { kind: "crate", points: 25, xp: 30 });
    expect(of("sendMessage")[0]?.args[1]).toBe(DROP_TEXT);
    const row = await env.DB.prepare("SELECT message_id FROM drops WHERE id = ?").bind(dropId).first<{ message_id: number }>();
    expect(row?.message_id).toBeGreaterThan(0);

    const users = Array.from({ length: 12 }, (_, i) => 1000 + i);
    const results = await Promise.all(users.map((u) => claimDrop(env, dropId, u)));
    const winners = results.filter((r) => r.outcome === "won");
    expect(winners).toHaveLength(1);
    expect(results.filter((r) => r.outcome === "late")).toHaveLength(users.length - 1);
    // a second wave is all late
    const again = await Promise.all(users.map((u) => claimDrop(env, dropId, u)));
    expect(again.every((r) => r.outcome === "late")).toBe(true);
  });

  it("settles crate, trap (clamped), and saver idempotently", async () => {
    const cfg = testCfg();
    const { api } = fakeApi();
    await seedMember(1, { balance: 4 });
    const crate = await spawnDrop(env, api, -1001, { kind: "crate", points: 20, xp: 30 });
    const c = await claimDrop(env, crate, 1);
    expect(c.outcome).toBe("won");
    await settleDrop(env, cfg, c.drop!, { id: 1, first_name: "A" });
    await settleDrop(env, cfg, c.drop!, { id: 1, first_name: "A" }); // replay is a no-op
    expect(await balance(1)).toBe(24);

    const trap = await spawnDrop(env, api, -1001, { kind: "trap", points: -100, xp: 0 });
    const t = await claimDrop(env, trap, 1);
    const res = await settleDrop(env, cfg, t.drop!, { id: 1, first_name: "A" });
    expect(await balance(1)).toBe(0);
    expect(res.text).toContain("24");

    const saver = await spawnDrop(env, api, -1001, { kind: "saver", points: 0, xp: 30 });
    const s = await claimDrop(env, saver, 1);
    await settleDrop(env, cfg, s.drop!, { id: 1, first_name: "A" });
    for (let i = 0; i < 3; i++) {
      const id = await spawnDrop(env, api, -1001, { kind: "saver", points: 0, xp: 30 });
      await settleDrop(env, cfg, (await claimDrop(env, id, 1)).drop!, { id: 1, first_name: "A" });
    }
    const st = await env.DB.prepare("SELECT savers FROM streaks WHERE user_id = 1").first<{ savers: number }>();
    expect(st?.savers).toBe(MAX_SAVERS);
  });

  it("expired drops cannot be claimed", async () => {
    const { api } = fakeApi();
    const id = await spawnDrop(env, api, -1001, { kind: "crate", points: 10, xp: 1 });
    await env.DB.prepare("UPDATE drops SET expires_at = ? WHERE id = ?").bind("2000-01-01T00:00:00.000Z", id).run();
    expect((await claimDrop(env, id, 5)).outcome).toBe("expired");
    expect((await claimDrop(env, 999999, 5)).outcome).toBe("missing");
  });
});
