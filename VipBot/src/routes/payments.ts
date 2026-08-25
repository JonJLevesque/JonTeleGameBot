import { Hono } from "hono";
import type { Env } from "../env";
import { PROCESSORS } from "../services/payments/fake";
import { handlePaymentEvent } from "../handlers/membership/payments";

export const paymentsRoute = new Hono<{ Bindings: Env }>();

paymentsRoute.post("/pay/:processor", async (c) => {
  const p = PROCESSORS[c.req.param("processor")];
  if (!p) return c.text("unknown processor", 404);
  const evt = await p.parseWebhook(c.env, c.req.raw);
  if (!evt) return c.text("bad signature", 400);
  const result = await handlePaymentEvent(c.env, c.executionCtx as unknown as ExecutionContext, evt);
  return c.json(result);
});
