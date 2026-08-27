export {};
/** Usage: TG_BOT_TOKEN=… TG_WEBHOOK_SECRET=… WORKER_URL=https://vipbot.<sub>.workers.dev npx tsx scripts/set-webhook.ts */
const token = process.env.TG_BOT_TOKEN!;
const secret = process.env.TG_WEBHOOK_SECRET!;
const url = process.env.WORKER_URL!;
const res = await fetch(`https://api.telegram.org/bot${token}/setWebhook`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    url: `${url}/tg/webhook`, secret_token: secret, drop_pending_updates: false,
    allowed_updates: ["message", "edited_message", "channel_post", "callback_query", "chat_member", "my_chat_member", "chat_join_request",
      "message_reaction", "poll_answer", "pre_checkout_query", "purchased_paid_media", "bot_subscription_updated"],
  }),
});
console.log(await res.json());
