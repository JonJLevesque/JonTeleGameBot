/** Cron dispatcher. Each feature exposes its own sweep; this maps schedules to them. */
import type { Env } from "../env";
import { loadConfig } from "../config";
import { reconcileMemberships } from "../handlers/membership/reconcile";
import { hourlySweep, weeklyReportGuard } from "./maintenance";
import { backupToR2 } from "./backup";

export async function runCron(env: Env, ctx: ExecutionContext, cron: string) {
  const cfg = await loadConfig(env);
  try {
    switch (cron) {
      case "*/5 * * * *": await reconcileMemberships(env, ctx, cfg); break;
      case "0 * * * *": await hourlySweep(env, cfg); await weeklyReportGuard(env, ctx, cfg); break;
      case "30 3 * * *": await backupToR2(env); break;
      default: console.warn("unknown cron", cron);
    }
  } catch (e) {
    console.error("cron failed", cron, String(e));
  }
}
