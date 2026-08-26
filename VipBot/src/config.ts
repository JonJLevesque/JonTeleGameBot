/** Runtime config: defaults here, overrides in the D1 `config` table (JSON values),
 *  cached in KV for 60s. Everything brandable lives here, not in code. */
import type { Env } from "./env";

export interface TierConfig {
  code: string;
  name: string;
  emoji: string;
  stars: number;         // Stars per 30 days
  usd: number;           // external rail price
  xpMultiplier: number;
  renewalPoints: number;
  voteWeight: number;
  /** Which rooms the tier unlocks. The channel (feed) is always included. */
  group: boolean;
}

export interface Config {
  communityName: string;
  creatorName: string;
  creatorTz: string;           // IANA, e.g. "America/Los_Angeles"
  pointsName: string;          // "Petals"
  pointsEmoji: string;
  xpName: string;              // "Heat"
  xpEmoji: string;
  groupChatId: number;         // 0 until configured via /setup
  channelChatId: number;
  gamesTopicId: number | null;
  tiers: TierConfig[];
  attestationVersion: number;
  graceDays: number;
  aiEnabled: boolean;
  aiModel: string;
  welcomePoints: number;
  economy: {
    messageXp: number; messageXpCooldownSec: number; messageXpDailyCap: number;
    reactionPoints: number; reactionXp: number; reactionDailyCap: number;
    claimBase: number; claimBonusCap: number; claimMultiplier: number; claimXp: number;
    streakMilestoneDays: number; streakMilestonePoints: number; streakMilestoneXp: number;
    dropMin: number; dropMax: number; dropXp: number; dropTrap: number; dropsPerDay: number;
    dropMsgMin: number; dropMsgMax: number; dropSaverChance: number; dropMinMsgsToTap: number;
    triviaPoints: number; triviaXp: number; triviaFastPoints: number; triviaFastXp: number; triviaOpenSec: number;
    tipXpPerStar: number; tipXpDailyCap: number; tipPointsPerStars: number;
    slotsMin: number; slotsMax: number; slotsCooldownSec: number; slotsDailyCap: number; slotsMinLevel: number;
    giveDailyCap: number; givePairCooldownMin: number; giveMinLevel: number; giveMinAgeDays: number;
  };
}

export const DEFAULT_CONFIG: Config = {
  communityName: "The Velvet Room",
  creatorName: "the creator",
  creatorTz: "America/Los_Angeles",
  pointsName: "Petals",
  pointsEmoji: "🌸",
  xpName: "Heat",
  xpEmoji: "🔥",
  groupChatId: 0,
  channelChatId: 0,
  gamesTopicId: null,
  tiers: [
    { code: "vip", name: "VIP", emoji: "🌸", stars: 500, usd: 9.99, xpMultiplier: 1, renewalPoints: 100, voteWeight: 1, group: false },
    { code: "vipplus", name: "VIP+", emoji: "🌹", stars: 1500, usd: 24.99, xpMultiplier: 1.5, renewalPoints: 400, voteWeight: 2, group: true },
  ],
  attestationVersion: 1,
  graceDays: 3,
  aiEnabled: false,
  aiModel: "claude-opus-5",
  welcomePoints: 20,
  economy: {
    messageXp: 5, messageXpCooldownSec: 60, messageXpDailyCap: 40,
    reactionPoints: 1, reactionXp: 2, reactionDailyCap: 20,
    claimBase: 2, claimBonusCap: 5, claimMultiplier: 5, claimXp: 20,
    streakMilestoneDays: 7, streakMilestonePoints: 25, streakMilestoneXp: 50,
    dropMin: 15, dropMax: 40, dropXp: 30, dropTrap: 10, dropsPerDay: 3,
    dropMsgMin: 35, dropMsgMax: 60, dropSaverChance: 0.1, dropMinMsgsToTap: 3,
    triviaPoints: 5, triviaXp: 15, triviaFastPoints: 10, triviaFastXp: 25, triviaOpenSec: 45,
    tipXpPerStar: 1, tipXpDailyCap: 2000, tipPointsPerStars: 5,
    slotsMin: 5, slotsMax: 50, slotsCooldownSec: 30, slotsDailyCap: 40, slotsMinLevel: 3,
    giveDailyCap: 100, givePairCooldownMin: 15, giveMinLevel: 2, giveMinAgeDays: 3,
  },
};

const KV_KEY = "config:v1";

export async function loadConfig(env: Env): Promise<Config> {
  const cached = await env.KV.get(KV_KEY, "json").catch(() => null);
  if (cached) return cached as Config;
  const rows = await env.DB.prepare("SELECT key, value_json FROM config").all<{ key: string; value_json: string }>();
  const cfg: Config = structuredClone(DEFAULT_CONFIG);
  for (const r of rows.results) {
    try { setPath(cfg as unknown as Record<string, unknown>, r.key, JSON.parse(r.value_json)); } catch { /* ignore bad row */ }
  }
  // Stored tiers may predate newer fields (e.g. `group`): fill gaps from the defaults by code.
  cfg.tiers = cfg.tiers.map((t) => ({ ...(DEFAULT_CONFIG.tiers.find((d) => d.code === t.code) ?? {}), ...t } as TierConfig));
  await env.KV.put(KV_KEY, JSON.stringify(cfg), { expirationTtl: 60 }).catch(() => {});
  return cfg;
}

export async function setConfig(env: Env, key: string, value: unknown): Promise<void> {
  await env.DB.prepare("INSERT INTO config (key, value_json) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value_json = excluded.value_json")
    .bind(key, JSON.stringify(value)).run();
  await env.KV.delete(KV_KEY).catch(() => {});
}

/** "economy.dropMax" -> cfg.economy.dropMax = value */
function setPath(obj: Record<string, unknown>, path: string, value: unknown) {
  const parts = path.split(".");
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i]!;
    if (typeof cur[p] !== "object" || cur[p] === null) cur[p] = {};
    cur = cur[p] as Record<string, unknown>;
  }
  cur[parts[parts.length - 1]!] = value;
}

export function tierByCode(cfg: Config, code: string | null | undefined): TierConfig | undefined {
  return cfg.tiers.find((t) => t.code === code);
}

/** True when the tier admits the member to the group (the channel is always included). */
export function tierAllowsGroup(cfg: Config, code: string | null | undefined): boolean {
  return tierByCode(cfg, code)?.group ?? false;
}

export function tierAccessLabel(t: TierConfig): string {
  return t.group ? "📸 feed + 💬 room" : "📸 feed";
}

export function isAdmin(env: Env, userId: number | undefined): boolean {
  if (!userId) return false;
  return env.ADMIN_USER_IDS.split(",").map((s) => s.trim()).includes(String(userId));
}
