/** Daily claim. Dates are YYYY-MM-DD strings in the creator's timezone; the caller computes them. */
export interface StreakState { current: number; best: number; lastClaimDate: string | null; savers: number }

export interface ClaimResult {
  ok: boolean;               // false = already claimed today
  streak: number;
  usedSaver: boolean;
  milestone: boolean;
  points: number;
  xp: number;
  state: StreakState;
}

export interface ClaimRules {
  base: number; bonusCap: number; multiplier: number; xp: number;
  milestoneDays: number; milestonePoints: number; milestoneXp: number;
}

export function dayDiff(a: string, b: string): number {
  return Math.round((Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / 86400000);
}

export function claimReward(streak: number, r: ClaimRules): number {
  return (r.base + Math.min(streak - 1, r.bonusCap)) * r.multiplier;
}

export function applyClaim(s: StreakState, today: string, r: ClaimRules): ClaimResult {
  const base = { usedSaver: false, milestone: false };
  if (s.lastClaimDate === today) {
    return { ok: false, streak: s.current, points: 0, xp: 0, state: s, ...base };
  }
  let current: number;
  let usedSaver = false;
  let savers = s.savers;
  const gap = s.lastClaimDate ? dayDiff(s.lastClaimDate, today) : Infinity;
  if (gap === 1) current = s.current + 1;
  else if (gap === 2 && savers > 0) { current = s.current + 1; usedSaver = true; savers -= 1; }
  else current = 1;
  const milestone = r.milestoneDays > 0 && current % r.milestoneDays === 0;
  const points = claimReward(current, r) + (milestone ? r.milestonePoints : 0);
  const xp = r.xp + (milestone ? r.milestoneXp : 0);
  return {
    ok: true, streak: current, usedSaver, milestone, points, xp,
    state: { current, best: Math.max(s.best, current), lastClaimDate: today, savers },
  };
}
