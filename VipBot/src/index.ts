import { Hono } from "hono";
import type { AiJob, Env, TgOp } from "./env";
import { telegramRoute } from "./routes/telegram";
import { paymentsRoute } from "./routes/payments";
import { healthRoute } from "./routes/health";
import { consumeAiJob } from "./jobs/ai";
import { consumeTgOp } from "./jobs/tgops";
import { runCron } from "./jobs/cron";

export { ChatDO } from "./do/ChatDO";
export { MemberDO } from "./do/MemberDO";

const app = new Hono<{ Bindings: Env }>();
app.route("/", healthRoute);
app.route("/", telegramRoute);
app.route("/", paymentsRoute);
app.notFound((c) => c.text("not found", 404));

export default {
  fetch: app.fetch,

  async queue(batch: MessageBatch<unknown>, env: Env, ctx: ExecutionContext) {
    for (const msg of batch.messages) {
      try {
        if (batch.queue.endsWith("ai-jobs")) await consumeAiJob(env, ctx, msg.body as AiJob);
        else await consumeTgOp(env, ctx, msg.body as TgOp);
        msg.ack();
      } catch (e) {
        console.error("queue job failed", batch.queue, String(e));
        msg.retry({ delaySeconds: 30 });
      }
    }
  },

  async scheduled(event: ScheduledController, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(runCron(env, ctx, event.cron));
  },
} satisfies ExportedHandler<Env>;
