/** Trivia rounds (quiz polls) and the creator's question bank. */
import type { Api } from "grammy";
import type { Config } from "../../config";
import type { Env } from "../../env";
import { nowIso } from "../../db";
import { chatStub } from "../../do/ChatDO";
import { shuffleQuiz, STATIC_BANK, triviaPayout, validQuiz, type Quiz } from "../../domain/trivia";
import { applyPoints, applyXp } from "../../services/ledger";
import { esc, groupSay, mention } from "../../services/telegram";
import { fmtPoints, isEarningMember } from "./common";

export interface BankRow { id: number; question: string; options_json: string; source: "creator" | "ai" | "static"; approved: number; used_at: string | null; created_at: string }
export interface RoundRow { id: number; chat_id: number; poll_id: string | null; message_id: number | null; bank_id: number | null; correct_idx: number; started_at: string; closes_at: string; closed_at: string | null; winners_json: string }

export function triviaRules(cfg: Config) {
  const e = cfg.economy;
  return { points: e.triviaPoints, xp: e.triviaXp, fastPoints: e.triviaFastPoints, fastXp: e.triviaFastXp };
}

/** Prefer approved, unused bank rows (creator first, then AI); fall back to the static bank. */
export async function pickQuestion(env: Env, topic?: string, rng: () => number = Math.random): Promise<{ quiz: Quiz; bankId: number | null } | null> {
  const like = topic ? `%${topic}%` : null;
  const row = await env.DB.prepare(
    `SELECT * FROM trivia_bank WHERE approved = 1 AND used_at IS NULL AND source IN ('creator','ai') ${like ? "AND question LIKE ?" : ""}
     ORDER BY CASE source WHEN 'creator' THEN 0 ELSE 1 END, RANDOM() LIMIT 1`,
  ).bind(...(like ? [like] : [])).first<BankRow>();
  if (row) {
    try {
      const options = JSON.parse(row.options_json) as string[];
      const quiz = shuffleQuiz({ question: row.question, options }, rng);
      if (validQuiz(quiz)) return { quiz, bankId: row.id };
    } catch { /* fall through to static */ }
  }
  if (STATIC_BANK.length === 0) return null;
  const base = STATIC_BANK[Math.floor(rng() * STATIC_BANK.length)]!;
  return { quiz: shuffleQuiz(base, rng), bankId: null };
}

export type StartResult = { ok: true; roundId: number } | { ok: false; reason: "no_question" | "already_open" | "send_failed" };

export async function startTriviaRound(env: Env, cfg: Config, api: Api, chatId: number, opts: { topic?: string; threadId?: number } = {}): Promise<StartResult> {
  const stub = chatStub(env, chatId);
  if (await stub.getOpenTrivia()) return { ok: false, reason: "already_open" };
  const picked = await pickQuestion(env, opts.topic);
  if (!picked) return { ok: false, reason: "no_question" };
  const { quiz, bankId } = picked;
  const openSec = Math.max(5, Math.min(600, cfg.economy.triviaOpenSec));
  const startedAt = new Date();
  const closesAt = new Date(startedAt.getTime() + openSec * 1000).toISOString();

  let pollId: string; let messageId: number;
  try {
    const msg = await api.sendPoll(chatId, `🧠 ${quiz.question}`, quiz.options.map((text) => ({ text })), {
      type: "quiz", correct_option_ids: [quiz.correctIdx], open_period: openSec, is_anonymous: false, message_thread_id: opts.threadId,
    });
    pollId = msg.poll.id; messageId = msg.message_id;
  } catch (e) {
    console.warn("sendPoll failed", String(e));
    return { ok: false, reason: "send_failed" };
  }

  const ins = await env.DB.prepare(
    "INSERT INTO trivia_rounds (chat_id, poll_id, message_id, bank_id, correct_idx, started_at, closes_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
  ).bind(chatId, pollId, messageId, bankId, quiz.correctIdx, startedAt.toISOString(), closesAt).run();
  const roundId = Number(ins.meta.last_row_id);
  const opened = await stub.openTrivia({ roundId, pollId, correctIdx: quiz.correctIdx, winners: [], closesAt });
  if (!opened) {
    // Lost the race with another /trivia; close this poll quietly.
    await api.stopPoll(chatId, messageId).catch(() => {});
    await env.DB.prepare("UPDATE trivia_rounds SET closed_at = ? WHERE id = ?").bind(nowIso(), roundId).run();
    return { ok: false, reason: "already_open" };
  }
  if (bankId) await env.DB.prepare("UPDATE trivia_bank SET used_at = ? WHERE id = ?").bind(nowIso(), bankId).run();
  return { ok: true, roundId };
}

export interface AnswerResult { paid: boolean; points: number; xp: number; first: boolean }

/** Called for every poll_answer. Pays immediately (quiz votes cannot be retracted). */
export async function handlePollAnswer(env: Env, cfg: Config, pollId: string, userId: number, optionIds: number[]): Promise<AnswerResult | null> {
  const round = await env.DB.prepare("SELECT * FROM trivia_rounds WHERE poll_id = ? AND closed_at IS NULL").bind(pollId).first<RoundRow>();
  if (!round) return null;
  if (optionIds.length !== 1 || optionIds[0] !== round.correct_idx) return { paid: false, points: 0, xp: 0, first: false };
  if (!(await isEarningMember(env, userId))) return { paid: false, points: 0, xp: 0, first: false };
  const pos = await chatStub(env, round.chat_id).triviaWinner(pollId, userId);
  if (pos < 0) return { paid: false, points: 0, xp: 0, first: false };
  const pay = triviaPayout(pos, triviaRules(cfg));
  const ref = `trivia:${round.id}:${userId}`;
  const r = await applyPoints(env, userId, pay.points, "trivia", { ref });
  await applyXp(env, userId, pay.xp, "trivia", ref);
  return { paid: r.applied, ...pay };
}

/** Runs from the TG_OPS `trivia_close` op that ChatDO's alarm enqueues. */
export async function closeTriviaRound(env: Env, _ctx: ExecutionContext, cfg: Config, api: Api, roundId: number, winners: number[]) {
  const upd = await env.DB.prepare("UPDATE trivia_rounds SET closed_at = ?, winners_json = ? WHERE id = ? AND closed_at IS NULL")
    .bind(nowIso(), JSON.stringify(winners), roundId).run();
  if ((upd.meta.changes ?? 0) === 0) return; // already closed (duplicate delivery)
  const round = await env.DB.prepare("SELECT * FROM trivia_rounds WHERE id = ?").bind(roundId).first<RoundRow>();
  if (!round) return;
  let text: string;
  if (winners.length === 0) {
    text = "🧠 Time's up. Nobody got it.";
  } else {
    const rows = winners.length
      ? await env.DB.prepare(`SELECT user_id, first_name FROM members WHERE user_id IN (${winners.map(() => "?").join(",")})`).bind(...winners).all<{ user_id: number; first_name: string }>()
      : { results: [] as { user_id: number; first_name: string }[] };
    const name = (id: number) => rows.results.find((r) => r.user_id === id)?.first_name ?? "someone";
    const rules = triviaRules(cfg);
    const lines = winners.slice(0, 10).map((id, i) => {
      const p = triviaPayout(i, rules);
      return `${i === 0 ? "🥇" : "✅"} ${mention(id, name(id))} +${p.points} ${cfg.pointsEmoji}`;
    });
    const more = winners.length > 10 ? `\n…and ${winners.length - 10} more` : "";
    text = `🧠 Round over. ${winners.length} got it right:\n${lines.join("\n")}${more}`;
  }
  try {
    if (round.chat_id === cfg.groupChatId) await groupSay(api, cfg, text, { threadId: null });
    else await api.sendMessage(round.chat_id, text, { parse_mode: "HTML" });
  } catch (e) {
    console.warn("trivia close message failed", String(e));
  }
}

// ---------- creator bank ----------

/** `/q add <question> | <correct> | <wrong> | <wrong> [| <wrong>]` */
export function parseQuestionLine(line: string): { question: string; options: string[] } | null {
  const parts = line.split("|").map((s) => s.trim()).filter(Boolean);
  if (parts.length < 3) return null;
  const [question, ...options] = parts;
  return { question: question!, options };
}

export async function addBankQuestion(env: Env, q: { question: string; options: string[] }, source: "creator" | "ai" = "creator"): Promise<number | null> {
  const quiz: Quiz = { question: q.question, options: q.options, correctIdx: 0 };
  if (!validQuiz(quiz)) return null;
  const ins = await env.DB.prepare("INSERT INTO trivia_bank (question, options_json, source, approved, created_at) VALUES (?, ?, ?, ?, ?)")
    .bind(q.question, JSON.stringify(q.options), source, source === "creator" ? 1 : 0, nowIso()).run();
  return Number(ins.meta.last_row_id);
}

export async function unapprovedQuestions(env: Env, limit = 5): Promise<BankRow[]> {
  const r = await env.DB.prepare("SELECT * FROM trivia_bank WHERE approved = 0 ORDER BY id LIMIT ?").bind(limit).all<BankRow>();
  return r.results;
}

export async function approveQuestion(env: Env, id: number): Promise<boolean> {
  const r = await env.DB.prepare("UPDATE trivia_bank SET approved = 1 WHERE id = ? AND approved = 0").bind(id).run();
  return (r.meta.changes ?? 0) > 0;
}

export async function rejectQuestion(env: Env, id: number): Promise<boolean> {
  const r = await env.DB.prepare("DELETE FROM trivia_bank WHERE id = ? AND approved = 0").bind(id).run();
  return (r.meta.changes ?? 0) > 0;
}

export async function bankCounts(env: Env) {
  const r = await env.DB.prepare(
    `SELECT source, approved, SUM(CASE WHEN used_at IS NULL THEN 1 ELSE 0 END) AS unused, COUNT(*) AS total FROM trivia_bank GROUP BY source, approved`,
  ).all<{ source: string; approved: number; unused: number; total: number }>();
  return r.results;
}

export function formatBankRow(r: BankRow): string {
  let opts: string[] = [];
  try { opts = JSON.parse(r.options_json); } catch { /* ignore */ }
  const [correct, ...wrong] = opts;
  return `#${r.id} <b>${esc(r.question)}</b>\n✅ ${esc(correct ?? "?")}\n${wrong.map((w) => `▫️ ${esc(w)}`).join("\n")}`;
}

export function fmtAnswerToast(cfg: Config, a: AnswerResult): string {
  return `✅ ${a.first ? "Fastest! " : ""}+${fmtPoints(cfg, a.points)}, +${a.xp} ${cfg.xpName}`;
}
