import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import { chatStub } from "../src/do/ChatDO";
import { addBankQuestion, closeTriviaRound, handlePollAnswer, parseQuestionLine, pickQuestion, startTriviaRound } from "../src/handlers/games/trivia";
import { fakeApi } from "./fakeApi";
import { balance, seedMember, testCfg } from "./games-shop-helpers";

const cfg = testCfg();
const CHAT = -1001;
const exec = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;

describe("trivia round", () => {
  it("bank preference: creator > ai > static; used rows are skipped", async () => {
    await env.DB.prepare("DELETE FROM trivia_bank").run();
    const ai = await addBankQuestion(env, { question: "AI q?", options: ["a", "b", "c"] }, "ai");
    await env.DB.prepare("UPDATE trivia_bank SET approved = 1 WHERE id = ?").bind(ai).run();
    const creator = await addBankQuestion(env, { question: "Creator q?", options: ["a", "b", "c"] }, "creator");
    expect((await pickQuestion(env))?.bankId).toBe(creator);
    await env.DB.prepare("UPDATE trivia_bank SET used_at = '2026-01-01' WHERE id = ?").bind(creator).run();
    expect((await pickQuestion(env))?.bankId).toBe(ai);
    await env.DB.prepare("UPDATE trivia_bank SET used_at = '2026-01-01' WHERE id = ?").bind(ai).run();
    const s = await pickQuestion(env);
    expect(s?.bankId).toBeNull();
    expect(s?.quiz.options[s.quiz.correctIdx]).toBeDefined();
    expect(parseQuestionLine("Q? | right | wrong")).toEqual({ question: "Q?", options: ["right", "wrong"] });
    expect(parseQuestionLine("Q? | only")).toBeNull();
  });

  it("full round: open, pay correct answers in order, close, summarize", async () => {
    const { api, of } = fakeApi();
    await seedMember(21, { balance: 0 });
    await seedMember(22, { balance: 0 });
    await seedMember(23, { balance: 0, state: "lapsed" });
    const start = await startTriviaRound(env, cfg, api, CHAT);
    expect(start.ok).toBe(true);
    if (!start.ok) return;
    const poll = of("sendPoll")[0]!;
    expect(poll.args[3]).toMatchObject({ type: "quiz", is_anonymous: false });
    const round = await env.DB.prepare("SELECT * FROM trivia_rounds WHERE id = ?").bind(start.roundId).first<{ poll_id: string; correct_idx: number }>();
    const pollId = round!.poll_id; const correct = round!.correct_idx;

    // second start is rejected while open
    expect(await startTriviaRound(env, cfg, api, CHAT)).toEqual({ ok: false, reason: "already_open" });

    const wrong = (correct + 1) % 4;
    expect((await handlePollAnswer(env, cfg, pollId, 21, [wrong]))?.paid).toBe(false);
    const a1 = await handlePollAnswer(env, cfg, pollId, 21, [correct]);
    expect(a1).toMatchObject({ paid: true, first: true, points: 15, xp: 40 });
    const a2 = await handlePollAnswer(env, cfg, pollId, 22, [correct]);
    expect(a2).toMatchObject({ paid: true, first: false, points: 5, xp: 15 });
    expect((await handlePollAnswer(env, cfg, pollId, 22, [correct]))?.paid).toBe(false); // duplicate
    expect((await handlePollAnswer(env, cfg, pollId, 23, [correct]))?.paid).toBe(false); // lapsed
    expect(await handlePollAnswer(env, cfg, "unknown-poll", 21, [0])).toBeNull();
    expect(await balance(21)).toBe(15);
    expect(await balance(22)).toBe(5);

    const open = await chatStub(env, CHAT).closeTrivia();
    expect(open?.winners).toEqual([21, 22]);
    await closeTriviaRound(env, exec, cfg, api, start.roundId, open!.winners);
    const closed = await env.DB.prepare("SELECT closed_at, winners_json FROM trivia_rounds WHERE id = ?").bind(start.roundId).first<{ closed_at: string; winners_json: string }>();
    expect(closed?.closed_at).toBeTruthy();
    expect(JSON.parse(closed!.winners_json)).toEqual([21, 22]);
    const summary = of("sendMessage").at(-1)!;
    expect(String(summary.args[1])).toContain("🥇");
    // duplicate close delivery is a no-op
    const n = of("sendMessage").length;
    await closeTriviaRound(env, exec, cfg, api, start.roundId, open!.winners);
    expect(of("sendMessage").length).toBe(n);
    // answers after close don't pay
    expect((await handlePollAnswer(env, cfg, pollId, 21, [correct]))).toBeNull();

    // a new round can open; nobody answers → "Nobody got it."
    const s2 = await startTriviaRound(env, cfg, api, CHAT);
    expect(s2.ok).toBe(true);
    const t2 = await chatStub(env, CHAT).closeTrivia();
    await closeTriviaRound(env, exec, cfg, api, (s2 as { roundId: number }).roundId, t2!.winners);
    expect(String(of("sendMessage").at(-1)!.args[1])).toContain("Nobody");
  });
});
