import { describe, expect, it } from "vitest";
import { shuffleQuiz, triviaPayout, validQuiz } from "../src/domain/trivia";

describe("trivia", () => {
  it("shuffle keeps track of the correct answer", () => {
    let seed = 7;
    const rng = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
    for (let i = 0; i < 50; i++) {
      const q = shuffleQuiz({ question: "q", options: ["right", "a", "b", "c"] }, rng);
      expect(q.options[q.correctIdx]).toBe("right");
      expect(validQuiz(q)).toBe(true);
    }
  });
  it("fastest gets bonus", () => {
    const r = { points: 5, xp: 15, fastPoints: 10, fastXp: 25 };
    expect(triviaPayout(0, r)).toEqual({ points: 15, xp: 40, first: true });
    expect(triviaPayout(1, r)).toEqual({ points: 5, xp: 15, first: false });
  });
});
