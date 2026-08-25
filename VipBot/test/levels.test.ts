import { describe, expect, it } from "vitest";
import { levelForXp, progressBar, titleFor, xpForLevel } from "../src/domain/levels";

describe("levels", () => {
  it("triangular thresholds", () => {
    expect(xpForLevel(1)).toBe(150);
    expect(xpForLevel(2)).toBe(450);
    expect(xpForLevel(10)).toBe(8250);
  });
  it("levelForXp is the inverse at every boundary", () => {
    for (let n = 0; n <= 40; n++) {
      expect(levelForXp(xpForLevel(n))).toBe(n);
      expect(levelForXp(xpForLevel(n + 1) - 1)).toBe(n);
    }
    expect(levelForXp(0)).toBe(0);
  });
  it("titles clamp", () => {
    expect(titleFor(0).title).toBe("Newcomer");
    expect(titleFor(99).title).toBe("Eternal");
  });
  it("progress bar", () => {
    const p = progressBar(150 + 150); // halfway from L1 (150) to L2 (450)
    expect(p.level).toBe(1);
    expect(p.bar).toBe("▰▰▰▰▰▱▱▱▱▱");
  });
});
