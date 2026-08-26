/** Plain-text questions from an admin in DM are answered from the manual; feature requests get filed. */
import type { Bot } from "grammy";
import type { Ctx } from "../../context";
import { nowIso } from "../../db";
import { answerOperator } from "../../services/ai";
import { dm, esc } from "../../services/telegram";
import { manual } from "./manual";

const DEVELOPER_ID = 7351823375;

export async function fileRequest(ctx: Ctx, text: string): Promise<number> {
  const r = await ctx.env.DB.prepare("INSERT INTO feature_requests (user_id, name, text, created_at) VALUES (?, ?, ?, ?)")
    .bind(ctx.from!.id, ctx.from!.first_name, text.slice(0, 1000), nowIso()).run();
  const id = Number(r.meta.last_row_id);
  await dm(ctx.api, DEVELOPER_ID, `📮 <b>Request #${id}</b> from ${esc(ctx.from!.first_name)} (${ctx.cfg.communityName}):\n${esc(text.slice(0, 1000))}`);
  return id;
}

export function registerAssistant(bot: Bot<Ctx>) {
  bot.command("request", async (ctx) => {
    if (ctx.chat.type !== "private" || !ctx.from) return;
    const text = (ctx.match ? String(ctx.match) : "").trim();
    if (!text) { await ctx.reply("Tell me what you'd like changed or added: /request <what and why>"); return; }
    const id = await fileRequest(ctx, text);
    await ctx.reply(`Filed as #${id} and sent to Jon. I'll let you know when it lands.`);
  });

  bot.command("requests", async (ctx) => {
    if (ctx.chat.type !== "private" || !ctx.isAdmin) return;
    const rows = await ctx.env.DB.prepare("SELECT id, name, text, status, created_at FROM feature_requests ORDER BY id DESC LIMIT 30")
      .all<{ id: number; name: string; text: string; status: string; created_at: string }>();
    if (!rows.results.length) { await ctx.reply("No requests yet."); return; }
    const icon = { open: "🟡", done: "✅", declined: "⛔" } as Record<string, string>;
    await ctx.reply(rows.results.map((r) => `${icon[r.status] ?? "•"} <b>#${r.id}</b> ${esc(r.text.slice(0, 120))} <i>— ${esc(r.name)}, ${r.created_at.slice(0, 10)}</i>`).join("\n"), { parse_mode: "HTML" });
  });

  // Free-text in an admin's DM → the manual answers. Runs after the command handlers; passes
  // through anything that isn't an admin DM or that the shop's pending-title step is waiting for.
  bot.on("message:text", async (ctx, next) => {
    if (ctx.chat.type !== "private" || !ctx.isAdmin || !ctx.from) return next();
    if (ctx.message.text.startsWith("/")) return next();
    if (await ctx.env.KV.get(`pending_title:${ctx.from.id}`)) return next();
    const question = ctx.message.text.trim();
    const histKey = `opchat:${ctx.from.id}`;
    const history = ((await ctx.env.KV.get(histKey, "json")) as { q: string; a: string }[] | null) ?? [];
    await ctx.api.sendChatAction(ctx.chat.id, "typing");
    const r = await answerOperator(ctx.env, ctx.cfg, manual(ctx.cfg), question, history);
    if (!r) {
      await ctx.reply("AI is off or unavailable right now — /help lists every command, or /request <text> to reach Jon.");
      return;
    }
    let reply = r.answer;
    if (r.request) {
      const id = await fileRequest(ctx, r.request);
      reply += `\n\n📮 Filed that as request #${id} for Jon.`;
    }
    await ctx.reply(reply, { parse_mode: "HTML" }).catch(() => ctx.reply(reply));
    history.push({ q: question.slice(0, 500), a: r.answer.slice(0, 700) });
    await ctx.env.KV.put(histKey, JSON.stringify(history.slice(-6)), { expirationTtl: 3600 });
  });
}
