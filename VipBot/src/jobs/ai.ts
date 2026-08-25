import { Api } from "grammy";
import type { AiJob, Env } from "../env";
import { loadConfig } from "../config";
import { generateTrivia, weeklySummary } from "../services/ai";
import { nowIso } from "../db";
import { dm } from "../services/telegram";

export async function consumeAiJob(env: Env, _ctx: ExecutionContext, job: AiJob) {
  const cfg = await loadConfig(env);
  const api = new Api(env.TG_BOT_TOKEN);
  switch (job.kind) {
    case "trivia_batch": {
      const recent = await env.DB.prepare("SELECT question FROM trivia_bank ORDER BY id DESC LIMIT 40").all<{ question: string }>();
      const quizzes = await generateTrivia(env, cfg, job.count, job.topic, recent.results.map((r) => r.question));
      if (!quizzes) { await dm(api, job.requestedBy, "Trivia generation failed (AI off or refused)."); return; }
      const stmt = env.DB.prepare("INSERT INTO trivia_bank (question, options_json, source, approved, created_at) VALUES (?, ?, 'ai', 0, ?)");
      await env.DB.batch(quizzes.filter((q) => q.options.length >= 2).map((q) => stmt.bind(q.question, JSON.stringify(q.options), nowIso())));
      await dm(api, job.requestedBy, `${quizzes.length} questions drafted. Review with /q review.`);
      break;
    }
    case "weekly_summary": {
      const s = await weeklySummary(env, cfg, job.statsJson);
      if (s) for (const id of env.ADMIN_USER_IDS.split(",")) await dm(api, Number(id.trim()), s);
      break;
    }
    case "moderate":
      // v2: AI screening
      break;
  }
}
