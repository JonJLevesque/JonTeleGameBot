import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG, type Config } from "../src/config";
import type { Ctx } from "../src/context";
import { getMember, upsertMember } from "../src/db";
import { getPoints, getXp } from "../src/services/ledger";
import { awardMessageXp, awardReaction, textHash, wordCount } from "../src/handlers/economy/xp";
import { doClaim } from "../src/handlers/economy/claim";
import { doGive } from "../src/handlers/economy/give";
import { recordTip } from "../src/handlers/economy/tips";
import { leaderboard, profileCard } from "../src/handlers/economy/profile";
import { DEFAULT_AWARDS, seedAwards } from "../src/handlers/economy/awards";

const cfg: Config = { ...structuredClone(DEFAULT_CONFIG), groupChatId: -100 };
const DAY = "2026-08-24";
const GROUP = -100;

function fakeCtx(day = DAY): Ctx {
  return { cfg, day, env, defer: () => {}, api: { sendMessage: async () => ({}), raw: { sendMessage: async () => ({}) } } } as unknown as Ctx;
}

async function member(id: number, state: "active" | "grace" | "lapsed" | null = "active", tier = "vip", joinedDaysAgo = 10) {
  await upsertMember(env, { id, first_name: `U${id}`, username: `u${id}` });
  await env.DB.prepare("UPDATE members SET joined_at = ? WHERE user_id = ?").bind(new Date(Date.now() - joinedDaysAgo * 86400000).toISOString(), id).run();
  if (state) await env.DB.prepare("INSERT INTO memberships (user_id, state, tier, last_transition_at) VALUES (?, ?, ?, ?)").bind(id, state, tier, new Date().toISOString()).run();
  return (await getMember(env, id))!;
}

describe("message XP", () => {
  it("hashes normalized text and counts words", async () => {
    expect(await textHash("Hello   World")).toBe(await textHash("hello world"));
    expect(wordCount("  a b  ")).toBe(2);
  });
  it("ignores short messages, non-members, duplicates; applies tier multiplier", async () => {
    const ctx = fakeCtx();
    await member(11, null);
    expect(await awardMessageXp(env, ctx, 11, GROUP, 1, "one two three")).toBeNull();
    await member(12, "active", "vipplus");
    expect(await awardMessageXp(env, ctx, 12, GROUP, 2, "hi")).toBeNull();
    expect(await awardMessageXp(env, ctx, 12, GROUP, 3, "one two three")).toBe(0);
    expect((await getXp(env, 12)).xp).toBe(Math.round(cfg.economy.messageXp * 1.5));
    // duplicate text → skipped; different text inside cooldown → skipped by counter
    expect(await awardMessageXp(env, ctx, 12, GROUP, 4, "ONE two   three")).toBeNull();
    expect(await awardMessageXp(env, ctx, 12, GROUP, 5, "a different message here")).toBeNull();
    expect((await getXp(env, 12)).xp).toBe(Math.round(cfg.economy.messageXp * 1.5));
  });
  it("is idempotent on chat:message ref", async () => {
    const ctx = fakeCtx();
    await member(13);
    await awardMessageXp(env, ctx, 13, GROUP, 9, "first proper message here");
    await env.KV.delete("lastmsg:13");
    await env.DB.prepare("DELETE FROM activity_counters WHERE user_id = 13").run();
    await awardMessageXp(env, ctx, 13, GROUP, 9, "first proper message here");
    expect((await getXp(env, 13)).xp).toBe(cfg.economy.messageXp);
  });
});

describe("reactions", () => {
  it("rewards the author once per reactor, never self", async () => {
    const ctx = fakeCtx();
    await member(21); await member(22);
    expect(await awardReaction(env, ctx, 21, 21, GROUP, 5)).toBe(false);
    expect(await awardReaction(env, ctx, 21, 22, GROUP, 5)).toBe(true);
    expect(await awardReaction(env, ctx, 21, 22, GROUP, 5)).toBe(false);
    expect((await getXp(env, 21)).xp).toBe(cfg.economy.reactionXp);
    expect(await getPoints(env, 21)).toBe(cfg.economy.reactionPoints);
  });
});

describe("/claim", () => {
  it("doubles the first claim, refuses same day, continues streak next day, idempotent", async () => {
    await member(31);
    const a = await doClaim(env, cfg, 31, "2026-08-24");
    expect(a.ok && a.first).toBe(true);
    const single = (cfg.economy.claimBase + 0) * cfg.economy.claimMultiplier;
    expect(a.points).toBe(single * 2);
    expect(a.xp).toBe(cfg.economy.claimXp * 2);
    expect(await getPoints(env, 31)).toBe(single * 2);
    const again = await doClaim(env, cfg, 31, "2026-08-24");
    expect(again.ok).toBe(false);
    const b = await doClaim(env, cfg, 31, "2026-08-25");
    expect(b.ok && !b.first && b.streak === 2).toBe(true);
    expect(await getPoints(env, 31)).toBe(single * 2 + (cfg.economy.claimBase + 1) * cfg.economy.claimMultiplier);
  });
  it("milestone at streakMilestoneDays", async () => {
    await member(32);
    let r;
    for (let d = 1; d <= cfg.economy.streakMilestoneDays; d++) r = await doClaim(env, cfg, 32, `2026-08-${String(d).padStart(2, "0")}`);
    expect(r!.milestone).toBe(true);
    expect(r!.xp).toBe(cfg.economy.claimXp + cfg.economy.streakMilestoneXp);
  });
});

describe("/give", () => {
  it("enforces level, age, balance, pair cooldown, reciprocity and daily cap", async () => {
    const giver = await member(41, "active", "vip", 10);
    const to = await member(42);
    expect(await doGive(env, cfg, giver, to, 5, 1)).toMatchObject({ ok: false, reason: expect.stringContaining("Level") });
    await env.DB.prepare("INSERT INTO xp_totals (user_id, xp, level) VALUES (41, 9999, 5)").run();
    const young = await member(43, "active", "vip", 0);
    await env.DB.prepare("INSERT INTO xp_totals (user_id, xp, level) VALUES (43, 9999, 5)").run();
    expect(await doGive(env, cfg, young, to, 5, 2)).toMatchObject({ ok: false, reason: expect.stringContaining("days") });
    expect(await doGive(env, cfg, giver, to, 5, 3)).toMatchObject({ ok: false, reason: "Not enough points." });
    await env.DB.prepare("INSERT INTO points_balances (user_id, balance) VALUES (41, 200) ON CONFLICT (user_id) DO UPDATE SET balance = 200").run();
    expect(await doGive(env, cfg, giver, to, cfg.economy.giveDailyCap + 1, 4)).toMatchObject({ ok: false, reason: expect.stringContaining("cap") });
    const ok = await doGive(env, cfg, giver, to, 30, 5);
    expect(ok).toEqual({ ok: true, fromBalance: 170 });
    expect(await getPoints(env, 42)).toBe(30);
    expect(await doGive(env, cfg, giver, to, 1, 6)).toMatchObject({ ok: false, reason: expect.stringContaining("recently") });
    // reciprocal blocked
    await env.DB.prepare("INSERT INTO xp_totals (user_id, xp, level) VALUES (42, 9999, 5)").run();
    expect(await doGive(env, cfg, to, giver, 1, 7)).toMatchObject({ ok: false, reason: expect.stringContaining("gave to you") });
  });
});

describe("tips", () => {
  it("records once per charge, converts stars to xp/points, caps xp daily", async () => {
    await member(51);
    const c: Config = { ...cfg, economy: { ...cfg.economy, tipXpDailyCap: 30, tipPointsPerStars: 5 } };
    const a = await recordTip(env, c, 51, 25, "ch1", DAY);
    expect(a).toMatchObject({ recorded: true, xp: 25, points: 5 });
    expect(await recordTip(env, c, 51, 25, "ch1", DAY)).toMatchObject({ recorded: false });
    const b = await recordTip(env, c, 51, 25, "ch2", DAY);
    expect(b.xp).toBe(5); // only 5 xp room left
    expect((await getXp(env, 51)).xp).toBe(30);
    expect(await getPoints(env, 51)).toBe(10);
    const pay = await env.DB.prepare("SELECT COUNT(*) AS n FROM payments WHERE user_id = 51 AND kind = 'stars_tip' AND external_txn_id = 'ch1'").first<{ n: number }>();
    expect(pay!.n).toBe(1);
  });
});

describe("profile & leaderboard", () => {
  it("renders a card with badges and a medal board", async () => {
    const m = await member(61, "active", "vipplus");
    await seedAwards(env);
    expect((await env.DB.prepare("SELECT COUNT(*) AS n FROM awards").first<{ n: number }>())!.n).toBe(DEFAULT_AWARDS.length);
    await env.DB.prepare("INSERT INTO member_awards (user_id, code, granted_at) VALUES (61, 'founder', '2026-01-01')").run();
    await env.DB.prepare("INSERT INTO xp_totals (user_id, xp, level) VALUES (61, 500, 2)").run();
    const card = await profileCard(env, cfg, m);
    expect(card).toContain("Curious");
    expect(card).toContain("VIP+");
    expect(card).toContain("Founder");
    const board = await leaderboard(env, cfg, "xp");
    expect(board).toContain("🥇");
    expect(board).toContain("U61");
  });
});
