/** Minimal execution context we pass around (hono and workers-types disagree on the full shape). */
export type Exec = { waitUntil(promise: Promise<unknown>): void };

export interface Env {
  ENVIRONMENT: string;
  DB: D1Database;
  KV: KVNamespace;
  BACKUPS: R2Bucket;
  AI_JOBS: Queue<AiJob>;
  TG_OPS: Queue<TgOp>;
  CHAT_DO: DurableObjectNamespace;
  MEMBER_DO: DurableObjectNamespace;
  // secrets
  TG_BOT_TOKEN: string;
  TG_WEBHOOK_SECRET: string;
  ANTHROPIC_API_KEY?: string;
  ADMIN_USER_IDS: string;
  CALLBACK_HMAC_KEY: string;
  PROCESSOR_FAKE_SECRET?: string;
}

/** Async AI work; consumed in src/jobs/ai.ts. */
export type AiJob =
  | { kind: "trivia_batch"; count: number; topic?: string; requestedBy: number }
  | { kind: "weekly_summary"; weekKey: string; statsJson: string }
  | { kind: "moderate"; chatId: number; messageId: number; userId: number; text: string };

/** Telegram side effects that must be paced or are bulk; consumed in src/jobs/tgops.ts. */
export type TgOp =
  | { kind: "kick"; userId: number; reason: string }
  | { kind: "unban"; userId: number }
  | { kind: "dm"; userId: number; text: string; parseMode?: "HTML" }
  | { kind: "broadcast"; text: string; parseMode?: "HTML"; actorId: number }
  | { kind: "group_message"; text: string; parseMode?: "HTML"; effectId?: string }
  | { kind: "ephemeral"; chatId: number; userId: number; text: string; replyTo?: number }
  | { kind: "trivia_close"; roundId: number; winners: number[] };
