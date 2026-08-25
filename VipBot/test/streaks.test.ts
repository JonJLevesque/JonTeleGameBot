import { describe, expect, it } from "vitest";
import { applyClaim, claimReward, type ClaimRules } from "../src/domain/streaks";

const R: ClaimRules = { base: 2, bonusCap: 5, multiplier: 5, xp: 20, milestoneDays: 7, milestonePoints: 25, milestoneXp: 50 };
const fresh = { current: 0, best: 0, lastClaimDate: null, savers: 0 };

describe("streaks", () => {
  it("reward scales then caps", () => {
    expect(claimReward(1, R)).toBe(10);
    expect(claimReward(6, R)).toBe(35);
    expect(claimReward(60, R)).toBe(35);
  });
  it("consecutive days extend, same day rejects, gap resets", () => {
    const a = applyClaim(fresh, "2026-03-07", R);
    expect(a.ok && a.streak).toBe(1);
    const b = applyClaim(a.state, "2026-03-08", R);
    expect(b.streak).toBe(2);
    expect(applyClaim(b.state, "2026-03-08", R).ok).toBe(false);
    expect(applyClaim(b.state, "2026-03-11", R).streak).toBe(1);
  });
  it("saver bridges exactly one missed day", () => {
    const s = { current: 4, best: 4, lastClaimDate: "2026-03-08", savers: 1 };
    const r = applyClaim(s, "2026-03-10", R);
    expect(r.streak).toBe(5);
    expect(r.usedSaver).toBe(true);
    expect(r.state.savers).toBe(0);
    expect(applyClaim(s, "2026-03-11", R).streak).toBe(1);
  });
  it("milestone pays extra", () => {
    const s = { current: 6, best: 6, lastClaimDate: "2026-03-08", savers: 0 };
    const r = applyClaim(s, "2026-03-09", R);
    expect(r.milestone).toBe(true);
    expect(r.points).toBe(35 + 25);
    expect(r.xp).toBe(70);
  });
  it("works across DST boundary dates (pure date strings)", () => {
    const s = { current: 1, best: 1, lastClaimDate: "2026-03-08", savers: 0 };
    expect(applyClaim(s, "2026-03-09", R).streak).toBe(2);
  });
});
