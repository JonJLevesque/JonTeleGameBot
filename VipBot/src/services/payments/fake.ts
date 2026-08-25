/** Test/staging processor: HMAC-SHA256 signed JSON webhooks. Lets the whole external
 *  rail be exercised end-to-end before a real merchant account exists. */
import type { Env } from "../../env";
import type { PaymentEvent, PaymentProcessor } from "./types";

async function hmacHex(secret: string, body: string): Promise<string> {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(body));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export const fakeProcessor: PaymentProcessor = {
  name: "fake",
  async checkoutUrl(_env, userId, tier) {
    return `https://example.invalid/checkout?user=${userId}&tier=${tier}`;
  },
  async parseWebhook(env, req) {
    const secret = env.PROCESSOR_FAKE_SECRET;
    if (!secret) return null;
    const body = await req.text();
    const sig = req.headers.get("x-signature") ?? "";
    if (sig !== (await hmacHex(secret, body))) return null;
    let j: Record<string, unknown>;
    try { j = JSON.parse(body); } catch { return null; }
    const kind = j.kind;
    if (kind !== "initial" && kind !== "rebill" && kind !== "refund" && kind !== "chargeback") return null;
    const ts = typeof j.occurred_at === "string" ? j.occurred_at : new Date().toISOString();
    if (Math.abs(Date.now() - Date.parse(ts)) > 5 * 60 * 1000) return null; // replay skew
    return {
      processor: "fake",
      eventId: String(j.event_id),
      txnId: j.txn_id ? String(j.txn_id) : undefined,
      kind,
      userId: Number(j.user_id),
      tier: String(j.tier ?? "vip"),
      amount: Number(j.amount ?? 0),
      currency: String(j.currency ?? "USD"),
      subscriptionId: j.subscription_id ? String(j.subscription_id) : undefined,
      periodEndAt: typeof j.period_end_at === "string" ? j.period_end_at : new Date(Date.now() + 30 * 86400000).toISOString(),
      occurredAt: ts,
      raw: j,
    } satisfies PaymentEvent;
  },
};

export const PROCESSORS: Record<string, PaymentProcessor> = { fake: fakeProcessor };
