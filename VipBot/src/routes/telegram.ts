import { Hono } from "hono";
import { webhookCallback } from "grammy";
import type { Env } from "../env";
import { dedupeUpdate } from "../db";
import { createBot } from "../bot";

export const telegramRoute = new Hono<{ Bindings: Env }>();

telegramRoute.post("/tg/webhook", async (c) => {
  const secret = c.req.header("X-Telegram-Bot-Api-Secret-Token") ?? "";
  if (!timingSafeEqual(secret, c.env.TG_WEBHOOK_SECRET)) return c.text("forbidden", 403);
  const body = await c.req.json<{ update_id?: number }>().catch(() => null);
  if (!body || typeof body.update_id !== "number") return c.text("bad request", 400);
  if (!(await dedupeUpdate(c.env, body.update_id))) return c.text("ok"); // Telegram retry
  const bot = await createBot(c.env, c.executionCtx as unknown as ExecutionContext);
  const handler = webhookCallback(bot, "cloudflare-mod", { timeoutMilliseconds: 8000, secretToken: c.env.TG_WEBHOOK_SECRET });
  // grammY needs the raw Request; rebuild it with the body we already consumed.
  const req = new Request(c.req.url, { method: "POST", headers: c.req.raw.headers, body: JSON.stringify(body) });
  return handler(req);
});

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}
