import type { Context } from "grammy";
import type { Config } from "./config";
import type { Env } from "./env";

/** Per-update context flavour attached in bot.ts. */
export interface AppFlavor {
  env: Env;
  cfg: Config;
  exec: ExecutionContext;
  /** YYYY-MM-DD in the creator's timezone at the time of the update. */
  day: string;
  isAdmin: boolean;
  /** Run after the 200 is sent (ctx.waitUntil). */
  defer: (p: Promise<unknown>) => void;
}
export type Ctx = Context & AppFlavor;
