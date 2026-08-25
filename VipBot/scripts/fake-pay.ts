/** Fire a signed fake-processor webhook at the Worker.
 *  Usage: PROCESSOR_FAKE_SECRET=… WORKER_URL=https://vipbot.<sub>.workers.dev \
 *         npx tsx scripts/fake-pay.ts <initial|rebill|refund|chargeback> <telegramUserId> [tier=vip] */
export {};

const [kind = "initial", userId, tier = "vip"] = process.argv.slice(2);
if (!userId) { console.error("need a user id"); process.exit(1); }
const secret = process.env.PROCESSOR_FAKE_SECRET!;
const url = process.env.WORKER_URL!;
const body = JSON.stringify({
  kind, user_id: Number(userId), tier, amount: 999, currency: "USD",
  event_id: `evt_${Date.now()}`, txn_id: `txn_${Date.now()}`, subscription_id: `sub_${userId}`,
  period_end_at: new Date(Date.now() + 30 * 86400000).toISOString(),
  occurred_at: new Date().toISOString(),
});
const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
const sig = [...new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body)))].map((b) => b.toString(16).padStart(2, "0")).join("");
const res = await fetch(`${url}/pay/fake`, { method: "POST", headers: { "content-type": "application/json", "x-signature": sig }, body });
console.log(res.status, await res.text());
