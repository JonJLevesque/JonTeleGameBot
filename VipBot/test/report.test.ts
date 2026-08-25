import { env } from "cloudflare:test";
import { describe, expect, it, vi } from "vitest";
import type { Api } from "grammy";
import { DEFAULT_CONFIG, type Config } from "../src/config";
import type { Env } from "../src/env";
import { upsertMember } from "../src/db";
import { applyPoints, applyXp } from "../src/services/ledger";
import { computeStats, formatStats } from "../src/handlers/admin/stats";
import { postWeeklyReport } from "../src/handlers/admin/report";
import { exportCsv } from "../src/handlers/admin/export";
import { tokenize } from "../src/handlers/admin/index";

const now = new Date().toISOString();

let seeded = false;
async function seed() {
  if (seeded) return;
  seeded = true;
  for (const [id, state] of [[1, "active"], [2, "active"], [3, "grace"], [4, "lapsed"]] as const) {
    await upsertMember(env, { id, first_name: `U${id}` });
    await env.DB.prepare("INSERT INTO memberships (user_id, state, tier, rail, last_transition_at) VALUES (?, ?, 'vip', 'stars', ?)").bind(id, state, now).run();
  }
  await env.DB.prepare("UPDATE members SET last_seen_at = ? WHERE user_id = 2").bind(new Date(Date.now() - 10 * 86400000).toISOString()).run();
  await env.DB.prepare("INSERT INTO payments (user_id, rail, external_event_id, kind, amount, currency, tier, occurred_at) VALUES (1, 'stars', 'e1', 'stars_sub', 500, 'XTR', 'vip', ?), (2, 'external', 'e2', 'initial', 999, 'USD', 'vip', ?), (2, 'external', 'e3', 'refund', 999, 'USD', 'vip', ?)").bind(now, now, now).run();
  await applyXp(env, 1, 10, "msg", "a:1");
  await applyXp(env, 1, 10, "msg", "a:2");
  await applyXp(env, 2, 50, "claim", "c:2");
  await applyPoints(env, 1, 40, "claim", { ref: "c1" });
  await applyPoints(env, 1, -15, "shop", { ref: "s1" });
  await env.DB.prepare("INSERT INTO purchases (user_id, item_id, price_paid, status, created_at) VALUES (1, 1, 10, 'queued', ?)").bind(now).run();
}

describe("stats", () => {
  it("computes the window summary", async () => {
    await seed();
    const s = await computeStats(env, 7);
    expect(s.members).toEqual({ active: 2, grace: 1, lapsed: 1, newMembers: 4, quiet: 1 });
    expect(s.messages).toBe(2);
    expect(s.points).toEqual({ issued: 40, sunk: 15 });
    expect(s.revenue).toEqual([
      { rail: "external", tier: "vip", currency: "USD", amount: 999, count: 1 },
      { rail: "stars", tier: "vip", currency: "XTR", amount: 500, count: 1 },
    ]);
    expect(s.topXp[0]).toMatchObject({ user_id: 2, xp: 50 });
    expect(s.openPurchases).toBe(1);
    const text = formatStats(s);
    expect(text).toContain("Active          2");
    expect(text).toContain("stars/vip: 500 XTR (1)");
    expect(text).not.toContain("<");
  });
});

describe("weekly report", () => {
  it("guards on week_key, DMs each admin, enqueues AI only when enabled", async () => {
    await seed();
    const sendMessage = vi.fn<(chatId: number, text: string) => Promise<unknown>>(async () => ({}));
    const api = { sendMessage } as unknown as Api;
    const send = vi.fn(async () => {});
    const fakeEnv = { ...env, ADMIN_USER_IDS: "1, 2", ANTHROPIC_API_KEY: "k", AI_JOBS: { send } } as unknown as Env;
    const cfg: Config = { ...structuredClone(DEFAULT_CONFIG), aiEnabled: false };
    expect(await postWeeklyReport(fakeEnv, {} as ExecutionContext, cfg, "2026-08-24", api)).toBe(true);
    expect(sendMessage).toHaveBeenCalledTimes(2);
    expect(sendMessage.mock.calls[0]![0]).toBe(1);
    expect(send).not.toHaveBeenCalled();
    const row = await env.DB.prepare("SELECT stats_json FROM reports WHERE week_key = '2026-08-24'").first<{ stats_json: string }>();
    expect(JSON.parse(row!.stats_json).members.active).toBe(2);
    // second run same week: no-op
    expect(await postWeeklyReport(fakeEnv, {} as ExecutionContext, cfg, "2026-08-24", api)).toBe(false);
    expect(sendMessage).toHaveBeenCalledTimes(2);
    // new week with AI on → enqueue
    expect(await postWeeklyReport(fakeEnv, {} as ExecutionContext, { ...cfg, aiEnabled: true }, "2026-08-31", api)).toBe(true);
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ kind: "weekly_summary", weekKey: "2026-08-31" }));
  });
});

describe("admin helpers", () => {
  it("exports CSV with quoting", async () => {
    await upsertMember(env, { id: 9, first_name: 'Quote "Q", Jr' });
    const csv = await exportCsv(env);
    expect(csv.split("\n")[0]).toContain("user_id,username,first_name");
    expect(csv).toContain('"Quote ""Q"", Jr"');
  });
  it("tokenizes quoted award names", () => {
    expect(tokenize('@bob "Night Owl" 10 5')).toEqual(["@bob", "Night Owl", "10", "5"]);
  });
});
