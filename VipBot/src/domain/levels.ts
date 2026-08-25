/** Triangular thresholds: cumulative XP to reach level n = 150·n·(n+1)/2. */
export const XP_PER_STEP = 150;

export function xpForLevel(level: number): number {
  return (XP_PER_STEP * level * (level + 1)) / 2;
}

export function levelForXp(xp: number): number {
  // Solve 75·n² + 75·n − xp ≤ 0 → n = floor((−1 + √(1 + 8·xp/150)) / 2)
  if (xp <= 0) return 0;
  const n = Math.floor((-1 + Math.sqrt(1 + (8 * xp) / XP_PER_STEP)) / 2);
  return xpForLevel(n + 1) <= xp ? n + 1 : n;
}

export interface LevelTitle { level: number; title: string; unlock?: string }

export const TITLES: LevelTitle[] = [
  { level: 0, title: "Newcomer" },
  { level: 1, title: "Newcomer" },
  { level: 2, title: "Curious", unlock: "You can now /give points to others." },
  { level: 3, title: "Regular", unlock: "Slots unlocked — /slots in the games topic." },
  { level: 4, title: "Admirer", unlock: "You can now vote in brackets." },
  { level: 5, title: "Devotee", unlock: "Custom title unlocked — /title <text>." },
  { level: 6, title: "Charmer", unlock: "5% shop discount." },
  { level: 7, title: "Confidant", unlock: "You pick one poll question a month." },
  { level: 8, title: "Muse", unlock: "A wallpaper pack is on its way." },
  { level: 9, title: "Flame", unlock: "A public shoutout in the channel." },
  { level: 10, title: "Silk", unlock: "A free streak saver every month." },
  { level: 11, title: "Velvet", unlock: "10% shop discount." },
  { level: 12, title: "Enchanter", unlock: "One free ask-me-anything ticket." },
  { level: 13, title: "Heartthrob", unlock: "Your name in a post credit." },
  { level: 14, title: "Legend", unlock: "A 10-minute DM slot." },
  { level: 15, title: "Eternal", unlock: "Permanent Hall of Fame entry." },
];

export function titleFor(level: number): LevelTitle {
  const clamped = Math.min(Math.max(level, 0), TITLES.length - 1);
  return TITLES[clamped]!;
}

export function shopDiscount(level: number): number {
  if (level >= 11) return 0.10;
  if (level >= 6) return 0.05;
  return 0;
}

/** Progress bar between the current level floor and the next threshold. */
export function progressBar(xp: number, cells = 10): { bar: string; level: number; into: number; span: number } {
  const level = levelForXp(xp);
  const floor = xpForLevel(level);
  const ceil = xpForLevel(level + 1);
  const into = xp - floor;
  const span = ceil - floor;
  const filled = Math.min(cells, Math.floor((into / span) * cells));
  return { bar: "▰".repeat(filled) + "▱".repeat(cells - filled), level, into, span };
}
