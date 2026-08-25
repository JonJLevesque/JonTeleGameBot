/** Award catalogue seeding (shared by economy profile and admin /award). */
import type { Env } from "../../env";

export const DEFAULT_AWARDS: Array<{ code: string; name: string; emoji: string; description: string }> = [
  { code: "first_night", name: "First Night", emoji: "🌙", description: "Joined and claimed on day one." },
  { code: "ten_crates", name: "Ten Crates", emoji: "📦", description: "Opened ten drops." },
  { code: "ironclad", name: "Ironclad", emoji: "🛡️", description: "30-day streak." },
  { code: "century", name: "Century", emoji: "💯", description: "100-day streak." },
  { code: "quiz_whiz", name: "Quiz Whiz", emoji: "🧠", description: "Ten trivia wins." },
  { code: "fastest_finger", name: "Fastest Finger", emoji: "⚡", description: "First correct answer five times." },
  { code: "patron", name: "Patron", emoji: "💎", description: "Tipped 500+ Stars." },
  { code: "founder", name: "Founder", emoji: "🏛️", description: "Among the first members." },
];

const KV_FLAG = "awards:seeded:v1";

export async function seedAwards(env: Env): Promise<void> {
  if (await env.KV.get(KV_FLAG).catch(() => null)) return;
  const stmt = env.DB.prepare("INSERT OR IGNORE INTO awards (code, name, emoji, description) VALUES (?, ?, ?, ?)");
  await env.DB.batch(DEFAULT_AWARDS.map((a) => stmt.bind(a.code, a.name, a.emoji, a.description)));
  await env.KV.put(KV_FLAG, "1", { expirationTtl: 7 * 86400 }).catch(() => {});
}

export function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "award";
}
