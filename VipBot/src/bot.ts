/** grammY bot factory. Feature modules register themselves; this file only wires. */
import { Bot } from "grammy";
import { loadConfig, isAdmin } from "./config";
import type { Ctx } from "./context";
import { localDay, upsertMember } from "./db";
import type { Env } from "./env";
import { registerFunnel } from "./handlers/funnel";
import { registerMembership } from "./handlers/membership";
import { registerEconomy } from "./handlers/economy";
import { registerGames } from "./handlers/games";
import { registerShop } from "./handlers/shop";
import { registerAdmin } from "./handlers/admin";

export async function createBot(env: Env, exec: ExecutionContext): Promise<Bot<Ctx>> {
  const cfg = await loadConfig(env);
  const bot = new Bot<Ctx>(env.TG_BOT_TOKEN, {
    botInfo: undefined, // fetched once per isolate via bot.init() in the route
  });

  bot.use(async (ctx, next) => {
    ctx.env = env;
    ctx.cfg = cfg;
    ctx.exec = exec;
    ctx.day = localDay(cfg.creatorTz);
    ctx.isAdmin = isAdmin(env, ctx.from?.id);
    ctx.defer = (p) => exec.waitUntil(p.catch((e) => console.error("deferred failed", String(e))));
    if (ctx.from && !ctx.from.is_bot) ctx.defer(upsertMember(env, ctx.from));
    await next();
  });

  // Order matters: admin first (DM-only, gated), then funnel (DM), membership events,
  // then economy observers, games, shop.
  registerAdmin(bot);
  registerFunnel(bot);
  registerMembership(bot);
  registerEconomy(bot);
  registerGames(bot);
  registerShop(bot);

  bot.catch((err) => {
    console.error("update error", err.error);
  });
  return bot;
}
