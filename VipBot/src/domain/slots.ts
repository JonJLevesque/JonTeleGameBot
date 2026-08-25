/** Telegram 🎰 dice: value 1..64 encodes three base-4 reels. RTP = 55/64 ≈ 0.859. */
export function reels(value: number): [number, number, number] {
  const v = value - 1;
  return [v & 3, (v >> 2) & 3, (v >> 4) & 3];
}

export function slotsMultiplier(value: number): number {
  if (value === 64) return 10;           // 7️⃣7️⃣7️⃣
  const [a, b, c] = reels(value);
  if (a === b && b === c) return 5;
  if (a === b) return 1.5;
  if (b === c) return 1;
  return 0;
}

export function slotsPayout(stake: number, value: number): number {
  return Math.floor(stake * slotsMultiplier(value));
}

/** Expected return per unit stake over all 64 equally likely outcomes. */
export function slotsRtp(): number {
  let total = 0;
  for (let v = 1; v <= 64; v++) total += slotsMultiplier(v);
  return total / 64;
}
