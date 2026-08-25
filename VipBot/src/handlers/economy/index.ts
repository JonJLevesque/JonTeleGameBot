/** Economy: passive XP, /claim, /profile, /leaderboard, /give, tips. Group-only except tips/profile in DM. */
import type { Bot } from "grammy";
import type { Ctx } from "../../context";
import { registerXp } from "./xp";
import { registerClaim } from "./claim";
import { registerProfile } from "./profile";
import { registerGive } from "./give";
import { registerTips } from "./tips";
import { seedAwards } from "./awards";

export function registerEconomy(bot: Bot<Ctx>) {
  bot.use(async (ctx, next) => {
    ctx.defer(seedAwards(ctx.env));
    await next();
  });
  registerXp(bot);
  registerClaim(bot);
  registerProfile(bot);
  registerGive(bot);
  registerTips(bot);
}
