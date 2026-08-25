import { Hono } from "hono";
import type { Env } from "../env";

export const healthRoute = new Hono<{ Bindings: Env }>();
healthRoute.get("/health", async (c) => {
  const db = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM memberships").first<{ n: number }>().catch(() => null);
  return c.json({ ok: !!db, env: c.env.ENVIRONMENT, members: db?.n ?? null });
});
