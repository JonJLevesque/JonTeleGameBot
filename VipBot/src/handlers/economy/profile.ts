/** /profile and /leaderboard. */
import type { Bot } from "grammy";
import type { Ctx } from "../../context";
import type { Env } from "../../env";
import type { Config } from "../../config";
import { tierByCode } from "../../config";
import { getMember, type MemberRow } from "../../db";
import { getPoints, getXp } from "../../services/ledger";
import { progressBar, titleFor } from "../../domain/levels";
import { esc, groupSay, mention } from "../../services/telegram";
import { getStreak } from "./claim";
import { JOIN_FIRST, argsOf, displayName, getMembership, hasRoom, inGroup, isEarning, quietReply, resolveTarget, upgradeLine } from "./common";

export async function profileCard(env: Env, cfg: Config, m: MemberRow): Promise<string> {
  const [{ xp }, points, streak, ms, awards] = await Promise.all([
    getXp(env, m.user_id), getPoints(env, m.user_id), getStreak(env, m.user_id), getMembership(env, m.user_id),
    env.DB.prepare("SELECT a.emoji, a.name FROM member_awards ma JOIN awards a ON a.code = ma.code WHERE ma.user_id = ? ORDER BY ma.granted_at")
      .bind(m.user_id).all<{ emoji: string; name: string }>(),
  ]);
  const p = progressBar(xp);
  const t = titleFor(p.level);
  const tier = tierByCode(cfg, ms?.tier);
  const lines = [
    `<b>${esc(displayName(m))}</b> — ${esc(t.title)} (Level ${p.level})`,
    `${p.bar} ${p.into}/${p.span}`,
    `${cfg.xpEmoji} ${xp} ${cfg.xpName} · ${cfg.pointsEmoji} ${points} ${cfg.pointsName}`,
    `🔥 Streak ${streak.current} (best ${streak.best})${streak.savers ? ` · 🛟 ${streak.savers}` : ""}`,
    `${tier ? `${tier.emoji} ${esc(tier.name)}` : "No tier"}${ms ? ` · ${esc(ms.state)}` : ""}`,
    `📅 Joined ${m.joined_at.slice(0, 10)}`,
  ];
  if (awards.results.length) lines.push(`🏅 ${awards.results.map((a) => `${a.emoji} ${esc(a.name)}`).join(" · ")}`);
  if (isEarning(ms) && !hasRoom(cfg, ms)) lines.push("", upgradeLine(cfg));
  return lines.join("\n");
}

export type BoardKind = "xp" | "points" | "streak";

export async function leaderboard(env: Env, cfg: Config, kind: BoardKind): Promise<string> {
  const sql = {
    xp: "SELECT m.user_id, m.first_name, x.xp AS v FROM xp_totals x JOIN members m ON m.user_id = x.user_id ORDER BY x.xp DESC LIMIT 10",
    points: "SELECT m.user_id, m.first_name, b.balance AS v FROM points_balances b JOIN members m ON m.user_id = b.user_id ORDER BY b.balance DESC LIMIT 10",
    streak: "SELECT m.user_id, m.first_name, s.current AS v FROM streaks s JOIN members m ON m.user_id = s.user_id ORDER BY s.current DESC LIMIT 10",
  }[kind];
  const rows = await env.DB.prepare(sql).all<{ user_id: number; first_name: string; v: number }>();
  const label = { xp: `${cfg.xpEmoji} ${cfg.xpName}`, points: `${cfg.pointsEmoji} ${cfg.pointsName}`, streak: "🔥 Streak" }[kind];
  if (!rows.results.length) return `<b>Leaderboard — ${label}</b>\nNobody yet.`;
  const medals = ["🥇", "🥈", "🥉"];
  const body = rows.results.map((r, i) => `${medals[i] ?? `${i + 1}.`} ${mention(r.user_id, r.first_name)} — <b>${r.v}</b>`).join("\n");
  return `<b>Leaderboard — ${label}</b>\n${body}`;
}

export function registerProfile(bot: Bot<Ctx>) {
  bot.command("profile", async (ctx) => {
    if (!ctx.from) return;
    if (ctx.chat.type !== "private" && !inGroup(ctx)) return;
    if (!isEarning(await getMembership(ctx.env, ctx.from.id))) { await quietReply(ctx, JOIN_FIRST); return; }
    const args = argsOf(ctx);
    let target: MemberRow | null = null;
    if (args[0]?.startsWith("@") || ctx.msg.reply_to_message) {
      const t = await resolveTarget(ctx, args);
      if (!t) { await quietReply(ctx, "I don't know that member yet."); return; }
      target = t.member;
    } else {
      target = await getMember(ctx.env, ctx.from.id);
    }
    if (!target) { await quietReply(ctx, "No profile yet — say hi in the group first."); return; }
    await quietReply(ctx, await profileCard(ctx.env, ctx.cfg, target));
  });

  bot.command("leaderboard", async (ctx) => {
    if (ctx.chat.type !== "private" && !inGroup(ctx)) return;
    if (!inGroup(ctx)) {
      const m = await getMembership(ctx.env, ctx.from!.id);
      if (!isEarning(m)) { await quietReply(ctx, JOIN_FIRST); return; }
      if (!hasRoom(ctx.cfg, m)) { await quietReply(ctx, `The leaderboard lives in the room. ${upgradeLine(ctx.cfg)}`); return; }
    }
    const arg = argsOf(ctx)[0]?.toLowerCase();
    const kind: BoardKind = arg === "points" || arg === "streak" ? arg : "xp";
    const text = await leaderboard(ctx.env, ctx.cfg, kind);
    if (inGroup(ctx)) await groupSay(ctx.api, ctx.cfg, text, { threadId: ctx.msg.message_thread_id ?? null });
    else await ctx.reply(text, { parse_mode: "HTML" });
  });
}
