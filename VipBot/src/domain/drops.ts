/** Drop pacing and rolling. State lives in ChatDO; this is the pure logic. */
export interface DropPacing { counter: number; threshold: number; day: string; spawnedToday: number }
export interface DropRules { msgMin: number; msgMax: number; perDay: number; min: number; max: number; xp: number; trap: number; saverChance: number }
export type Rng = () => number; // [0,1)

export function randInt(rng: Rng, lo: number, hi: number): number {
  return lo + Math.floor(rng() * (hi - lo + 1));
}

export function freshPacing(day: string, rules: DropRules, rng: Rng): DropPacing {
  return { counter: 0, threshold: randInt(rng, rules.msgMin, rules.msgMax), day, spawnedToday: 0 };
}

/** Register one human message. Returns the new state and whether a drop should spawn now. */
export function registerMessage(p: DropPacing, today: string, rules: DropRules, rng: Rng): { state: DropPacing; spawn: boolean } {
  let s = p.day === today ? { ...p } : freshPacing(today, rules, rng);
  s.counter += 1;
  if (s.counter < s.threshold) return { state: s, spawn: false };
  // threshold hit: always reset pacing so a capped day doesn't burst at midnight
  s = { ...s, counter: 0, threshold: randInt(rng, rules.msgMin, rules.msgMax) };
  if (s.spawnedToday >= rules.perDay) return { state: s, spawn: false };
  s.spawnedToday += 1;
  return { state: s, spawn: true };
}

export interface DropRoll { kind: "crate" | "trap" | "saver"; points: number; xp: number }

export function rollDrop(rules: DropRules, rng: Rng): DropRoll {
  const r = rng();
  if (r < 0.2) return { kind: "trap", points: -rules.trap, xp: 0 };
  if (r < 0.2 + rules.saverChance) return { kind: "saver", points: 0, xp: rules.xp };
  return { kind: "crate", points: randInt(rng, rules.min, rules.max), xp: rules.xp };
}

/** Trap loss can never exceed the balance. */
export function trapLoss(balance: number, trap: number): number {
  return Math.min(balance, trap);
}
