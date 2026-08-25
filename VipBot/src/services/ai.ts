/** Anthropic calls. Returns null on any failure/refusal; every caller must have a static fallback. */
import Anthropic from "@anthropic-ai/sdk";
import type { Config } from "../config";
import type { Env } from "../env";

export function aiEnabled(env: Env, cfg: Config): boolean {
  return cfg.aiEnabled && !!env.ANTHROPIC_API_KEY;
}

function client(env: Env) {
  return new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, timeout: 120_000, maxRetries: 1 });
}

async function create(env: Env, cfg: Config, params: Omit<Anthropic.Beta.Messages.MessageCreateParamsNonStreaming, "model" | "betas">) {
  if (!aiEnabled(env, cfg)) return null;
  try {
    const resp = await client(env).beta.messages.create({
      model: cfg.aiModel,
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
      ...params,
    });
    if (resp.stop_reason === "refusal") { console.warn("ai refusal", resp.stop_details); return null; }
    return resp;
  } catch (e) {
    console.error("ai call failed", String(e));
    return null;
  }
}

function text(resp: Anthropic.Beta.Messages.BetaMessage | null): string | null {
  if (!resp) return null;
  const t = resp.content.filter((b): b is Anthropic.Beta.Messages.BetaTextBlock => b.type === "text").map((b) => b.text).join("").trim();
  return t || null;
}

export interface GeneratedQuiz { question: string; options: string[] } // options[0] correct

export async function generateTrivia(env: Env, cfg: Config, count: number, topic?: string, avoid: string[] = []): Promise<GeneratedQuiz[] | null> {
  const schema = {
    type: "object",
    properties: { quizzes: { type: "array", items: { type: "object", properties: { question: { type: "string" }, options: { type: "array", items: { type: "string" } } }, required: ["question", "options"], additionalProperties: false } } },
    required: ["quizzes"], additionalProperties: false,
  };
  const prompt =
    `Write ${count} trivia questions for a playful adult fan community called "${cfg.communityName}" run by ${cfg.creatorName}. ` +
    (topic ? `Topic: ${topic}. ` : "Mix pop culture, tech, sex-positive facts (tasteful, never explicit), and general knowledge. ") +
    "Each question ≤ 250 chars, exactly 4 options each ≤ 90 chars, with the CORRECT option FIRST. Fun, specific, not trivial. " +
    (avoid.length ? `Avoid these already-used questions:\n- ${avoid.join("\n- ")}` : "");
  const resp = await create(env, cfg, {
    max_tokens: 4000,
    output_config: { effort: "low", format: { type: "json_schema", schema } },
    messages: [{ role: "user", content: prompt }],
  } as never);
  const t = text(resp);
  if (!t) return null;
  try { return (JSON.parse(t) as { quizzes: GeneratedQuiz[] }).quizzes; } catch { return null; }
}

export async function weeklySummary(env: Env, cfg: Config, statsJson: string): Promise<string | null> {
  const resp = await create(env, cfg, {
    max_tokens: 1500,
    output_config: { effort: "high" },
    messages: [{ role: "user", content:
      `You are the analytics brain for ${cfg.creatorName}'s paid Telegram community "${cfg.communityName}". ` +
      "From this week's raw stats (JSON), write a plain-text creator briefing under 180 words: what moved, who to thank, " +
      "one risk, and two concrete actions for next week. Direct, no fluff, no markdown.\n\n" + statsJson }],
  } as never);
  return text(resp);
}
