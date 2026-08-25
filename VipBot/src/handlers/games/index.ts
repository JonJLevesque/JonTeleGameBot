/** Games: drops (middleware + callback), trivia (command, poll answers, bank), slots. */
import type { Bot } from "grammy";
import { InlineKeyboard } from "grammy";
import type { Ctx } from "../../context";
import { audit, bumpCounter, getCounter } from "../../db";
import { chatStub } from "../../do/ChatDO";
import { signCb, verifyCb } from "../../domain/callbacks";
import { ephemeral, esc, groupSay, EFFECT } from "../../services/telegram";
import { fmtPoints, inDm, inGroup, isEarningMember, threadOf } from "./common";
import { claimDrop, dropRules, editDropMessage, EXPIRED_TEXT, settleDrop, spawnDrop } from "./drops";
import {
  addBankQuestion, approveQuestion, bankCounts, fmtAnswerToast, formatBankRow, handlePollAnswer, parseQuestionLine,
  rejectQuestion, startTriviaRound, unapprovedQuestions,
} from "./trivia";
import { parseStake, spin, spinErrorText, spinText } from "./slots";

/** Per-day message counter used for the "chat a little first" drop gate. */
export const MSGS_COUNTER = "msgs";
const MSGS_CAP = 1_000_000;

function args(ctx: Ctx): string[] {
  return (ctx.match?.toString() ?? "").trim().split(/\s+/).filter(Boolean);
}

async function say(ctx: Ctx, text: string) {
  if (inDm(ctx)) { await ctx.reply(text, { parse_mode: "HTML" }); return; }
  if (ctx.chat && ctx.from) await ephemeral(ctx.api, ctx.chat.id, ctx.from.id, text, { threadId: threadOf(ctx), replyTo: ctx.message?.message_id });
}

export function registerGames(bot: Bot<Ctx>) {
  // ---- drops: count human messages, spawn when ChatDO says so ----
  bot.on("message:text", async (ctx, next) => {
    if (inGroup(ctx) && ctx.from && !ctx.from.is_bot && !ctx.message.text.startsWith("/")) {
      const { env, cfg } = ctx;
      const chatId = ctx.chat.id;
      const threadId = threadOf(ctx);
      ctx.defer((async () => {
        await bumpCounter(env, ctx.from.id, ctx.day, MSGS_COUNTER, MSGS_CAP);
        const roll = await chatStub(env, chatId).registerMessage(ctx.day, dropRules(cfg));
        if (roll) await spawnDrop(env, ctx.api, chatId, roll, cfg.gamesTopicId ?? threadId);
      })());
    }
    await next();
  });

  bot.command("drop", async (ctx, next) => {
    if (!inGroup(ctx) || !ctx.isAdmin) return next();
    const roll = await chatStub(ctx.env, ctx.chat.id).forceDrop(dropRules(ctx.cfg));
    await spawnDrop(ctx.env, ctx.api, ctx.chat.id, roll, ctx.cfg.gamesTopicId ?? threadOf(ctx));
    await audit(ctx.env, ctx.from?.id ?? null, "drop.force", ctx.chat.id, { kind: roll.kind });
  });

  // ---- trivia ----
  bot.command("trivia", async (ctx, next) => {
    if (!inGroup(ctx) || !ctx.isAdmin) return next();
    const topic = args(ctx).join(" ") || undefined;
    const r = await startTriviaRound(ctx.env, ctx.cfg, ctx.api, ctx.chat.id, { topic, threadId: ctx.cfg.gamesTopicId ?? threadOf(ctx) });
    if (!r.ok) {
      const msg = r.reason === "already_open" ? "A round is already open." : r.reason === "no_question" ? "No questions available. Add some with /q add." : "Couldn't post the poll.";
      await say(ctx, msg);
    }
  });

  bot.on("poll_answer", async (ctx, next) => {
    const pa = ctx.pollAnswer;
    const user = pa.user;
    if (!user || user.is_bot) return next();
    const res = await handlePollAnswer(ctx.env, ctx.cfg, pa.poll_id, user.id, pa.option_ids ?? []);
    if (res?.paid && ctx.cfg.groupChatId) {
      await ephemeral(ctx.api, ctx.cfg.groupChatId, user.id, fmtAnswerToast(ctx.cfg, res), { threadId: ctx.cfg.gamesTopicId ?? undefined });
    }
    await next();
  });

  bot.command("q", async (ctx, next) => {
    if (!ctx.isAdmin || !(inDm(ctx) || inGroup(ctx))) return next();
    const raw = (ctx.match?.toString() ?? "").trim();
    const [sub, ...rest] = raw.split(/\s+/);
    const tail = raw.slice(sub?.length ?? 0).trim();
    switch (sub) {
      case "add": {
        const q = parseQuestionLine(tail);
        if (!q) return say(ctx, "Format: /q add &lt;question&gt; | &lt;correct&gt; | &lt;wrong&gt; | &lt;wrong&gt; [| &lt;wrong&gt;]");
        const id = await addBankQuestion(ctx.env, q, "creator");
        if (!id) return say(ctx, "Too long — question ≤290 chars, options ≤95 chars, 2–10 options.");
        await audit(ctx.env, ctx.from?.id ?? null, "trivia.add", id);
        return say(ctx, `Added #${id}.`);
      }
      case "review": {
        const rows = await unapprovedQuestions(ctx.env);
        if (rows.length === 0) return say(ctx, "Nothing to review.");
        for (const r of rows) {
          const kb = new InlineKeyboard()
            .text("✅ Keep", await signCb(ctx.env.CALLBACK_HMAC_KEY, "qok", String(r.id)))
            .text("🗑 Drop", await signCb(ctx.env.CALLBACK_HMAC_KEY, "qno", String(r.id)));
          if (inDm(ctx)) await ctx.reply(formatBankRow(r), { parse_mode: "HTML", reply_markup: kb });
          else if (ctx.from) await ctx.api.raw.sendMessage({ chat_id: ctx.chat.id, receiver_user_id: ctx.from.id, text: formatBankRow(r), parse_mode: "HTML", reply_markup: kb }).catch(() => {});
        }
        return;
      }
      case "ok": case "no": {
        const id = Number(rest[0]);
        if (!id) return say(ctx, `Usage: /q ${sub} &lt;id&gt;`);
        const done = sub === "ok" ? await approveQuestion(ctx.env, id) : await rejectQuestion(ctx.env, id);
        return say(ctx, done ? (sub === "ok" ? `#${id} approved.` : `#${id} deleted.`) : `#${id} not pending.`);
      }
      case "gen": {
        const n = Number.parseInt(rest[0] ?? "", 10);
        const count = Number.isFinite(n) && n > 0 ? Math.min(n, 30) : 10;
        const topic = (Number.isFinite(n) ? rest.slice(1) : rest).join(" ") || undefined;
        if (!ctx.cfg.aiEnabled) return say(ctx, "AI is off (config aiEnabled).");
        await ctx.env.AI_JOBS.send({ kind: "trivia_batch", count, topic, requestedBy: ctx.from!.id });
        return say(ctx, `Drafting ${count} questions${topic ? ` about ${esc(topic)}` : ""}. I'll DM you when they're ready.`);
      }
      case "count": {
        const rows = await bankCounts(ctx.env);
        if (rows.length === 0) return say(ctx, "Bank is empty (static fallback questions only).");
        const lines = rows.map((r) => `${r.source}${r.approved ? "" : " (pending)"}: ${r.unused} unused / ${r.total}`);
        return say(ctx, `<b>Trivia bank</b>\n${lines.join("\n")}`);
      }
      default:
        return say(ctx, "Trivia bank: /q add, /q review, /q ok &lt;id&gt;, /q no &lt;id&gt;, /q gen [N] [topic], /q count");
    }
  });

  // ---- slots ----
  bot.command("slots", async (ctx, next) => {
    if (!inGroup(ctx) || !ctx.from) return next();
    const { cfg } = ctx;
    if (cfg.gamesTopicId && threadOf(ctx) !== cfg.gamesTopicId) return say(ctx, "Slots live in the games topic.");
    if (!(await isEarningMember(ctx.env, ctx.from.id))) return say(ctx, "Members only.");
    const stake = parseStake(cfg, args(ctx)[0]);
    if (stake === null) return say(ctx, spinErrorText(cfg, { ok: false, reason: "bad_stake" }));
    const r = await spin(ctx.env, cfg, ctx.api, {
      chatId: ctx.chat.id, userId: ctx.from.id, day: ctx.day, stake, ref: String(ctx.update.update_id), threadId: threadOf(ctx),
    });
    if (!r.ok) return say(ctx, spinErrorText(cfg, r));
    await say(ctx, spinText(cfg, r));
    if (r.multiplier >= 5) {
      const who = esc(ctx.from.first_name);
      await groupSay(ctx.api, cfg, `🎰 ${who} hit ${r.reels} — <b>+${fmtPoints(cfg, r.win)}</b>!`, { effectId: EFFECT.party, threadId: threadOf(ctx) ?? null }).catch(() => {});
    }
  });

  // ---- callbacks: drop / qok / qno ----
  bot.on("callback_query:data", async (ctx, next) => {
    const v = await verifyCb(ctx.env.CALLBACK_HMAC_KEY, ctx.callbackQuery.data);
    if (!v || !["drop", "qok", "qno"].includes(v.kind)) return next();
    const uid = ctx.from.id;
    const cqid = ctx.callbackQuery.id;
    const { env, cfg } = ctx;

    if (v.kind === "qok" || v.kind === "qno") {
      if (!ctx.isAdmin) return ctx.answerCallbackQuery({ text: "Admins only." });
      const id = Number(v.payload);
      const done = v.kind === "qok" ? await approveQuestion(env, id) : await rejectQuestion(env, id);
      await ctx.answerCallbackQuery({ text: done ? (v.kind === "qok" ? "Approved" : "Deleted") : "Already handled" });
      if (done) await ctx.editMessageReplyMarkup({ reply_markup: undefined }).catch(() => {});
      return;
    }

    // drop
    const dropId = Number(v.payload);
    const chatId = ctx.chat?.id ?? cfg.groupChatId;
    if (!Number.isFinite(dropId)) return ctx.answerCallbackQuery();
    if (!(await isEarningMember(env, uid))) return ctx.answerCallbackQuery({ text: "Members only." });
    const msgsToday = await getCounter(env, uid, ctx.day, MSGS_COUNTER);
    if (msgsToday < cfg.economy.dropMinMsgsToTap) {
      return ephemeral(ctx.api, chatId, uid, `Chat a little first — ${cfg.economy.dropMinMsgsToTap} messages today unlocks crates.`, { callbackQueryId: cqid });
    }
    const { outcome, drop } = await claimDrop(env, dropId, uid);
    if (outcome === "won" && drop) {
      const res = await settleDrop(env, cfg, drop, { id: uid, first_name: ctx.from.first_name });
      await editDropMessage(ctx.api, drop, res.text);
      await ephemeral(ctx.api, chatId, uid, res.toast, { callbackQueryId: cqid });
      return;
    }
    if (outcome === "expired" && drop) {
      await editDropMessage(ctx.api, drop, EXPIRED_TEXT);
      return ctx.answerCallbackQuery({ text: "That crate expired." });
    }
    await ctx.answerCallbackQuery({ text: "Too slow — already claimed." });
  });
}
