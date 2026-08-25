import { describe, expect, it } from "vitest";
import { reels, slotsMultiplier, slotsPayout, slotsRtp } from "../src/domain/slots";

describe("slots", () => {
  it("decodes reels", () => {
    expect(reels(1)).toEqual([0, 0, 0]);
    expect(reels(64)).toEqual([3, 3, 3]);
  });
  it("RTP is exactly 55/64", () => {
    expect(slotsRtp()).toBeCloseTo(55 / 64, 10);
  });
  it("paytable", () => {
    expect(slotsMultiplier(64)).toBe(10);
    expect(slotsMultiplier(1)).toBe(5);
    expect(slotsPayout(10, 64)).toBe(100);
  });
});
