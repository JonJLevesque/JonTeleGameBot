import { describe, expect, it } from "vitest";
import { freshPacing, registerMessage, rollDrop, trapLoss, type DropRules } from "../src/domain/drops";

const R: DropRules = { msgMin: 35, msgMax: 60, perDay: 3, min: 15, max: 40, xp: 30, trap: 10, saverChance: 0.1 };
const seq = (vals: number[]) => { let i = 0; return () => vals[i++ % vals.length]!; };

describe("drops", () => {
  it("spawns at threshold, resets, and caps per day", () => {
    const rng = () => 0; // threshold = msgMin = 35
    let s = freshPacing("d1", R, rng);
    let spawns = 0;
    for (let i = 0; i < 35 * 5; i++) {
      const r = registerMessage(s, "d1", R, rng);
      s = r.state;
      if (r.spawn) spawns++;
    }
    expect(spawns).toBe(3);
    expect(s.counter).toBeLessThan(35); // pacing kept resetting even when capped
  });
  it("new day resets counters", () => {
    const rng = () => 0;
    let s = { ...freshPacing("d1", R, rng), spawnedToday: 3, counter: 34 };
    const r = registerMessage(s, "d2", R, rng);
    expect(r.state.spawnedToday).toBe(0);
    expect(r.state.counter).toBe(1);
  });
  it("roll distribution", () => {
    expect(rollDrop(R, seq([0.1])).kind).toBe("trap");
    expect(rollDrop(R, seq([0.25])).kind).toBe("saver");
    const c = rollDrop(R, seq([0.9, 0.5]));
    expect(c.kind).toBe("crate");
    expect(c.points).toBeGreaterThanOrEqual(15);
    expect(c.points).toBeLessThanOrEqual(40);
  });
  it("trap never exceeds balance", () => {
    expect(trapLoss(3, 10)).toBe(3);
    expect(trapLoss(50, 10)).toBe(10);
  });
});
