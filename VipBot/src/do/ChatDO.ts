/** One instance per Telegram chat. Owns drop pacing, the open trivia round, and
 *  per-chat rate limits — everything that must be serialized per chat. */
import { DurableObject } from "cloudflare:workers";
import type { Env } from "../env";
import { freshPacing, registerMessage, rollDrop, type DropPacing, type DropRoll, type DropRules } from "../domain/drops";

export interface OpenTrivia { roundId: number; pollId: string; correctIdx: number; winners: number[]; closesAt: string }

export class ChatDO extends DurableObject<Env> {
  /** Count a human message toward the next drop. Returns a roll when one should spawn. */
  async registerMessage(today: string, rules: DropRules): Promise<DropRoll | null> {
    const rng = Math.random;
    const prev = (await this.ctx.storage.get<DropPacing>("pacing")) ?? freshPacing(today, rules, rng);
    const { state, spawn } = registerMessage(prev, today, rules, rng);
    await this.ctx.storage.put("pacing", state);
    return spawn ? rollDrop(rules, rng) : null;
  }

  async forceDrop(rules: DropRules): Promise<DropRoll> {
    return rollDrop(rules, Math.random);
  }

  async getOpenTrivia(): Promise<OpenTrivia | null> {
    return (await this.ctx.storage.get<OpenTrivia>("trivia")) ?? null;
  }

  /** Open a round; returns false if one is already open. */
  async openTrivia(round: OpenTrivia): Promise<boolean> {
    if (await this.ctx.storage.get("trivia")) return false;
    await this.ctx.storage.put("trivia", round);
    await this.ctx.storage.setAlarm(Date.parse(round.closesAt) + 2000);
    return true;
  }

  /** Record a correct answer; returns the winner's position (0 = fastest) or -1 if not open / duplicate. */
  async triviaWinner(pollId: string, userId: number): Promise<number> {
    const t = await this.ctx.storage.get<OpenTrivia>("trivia");
    if (!t || t.pollId !== pollId || t.winners.includes(userId)) return -1;
    t.winners.push(userId);
    await this.ctx.storage.put("trivia", t);
    return t.winners.length - 1;
  }

  async closeTrivia(): Promise<OpenTrivia | null> {
    const t = (await this.ctx.storage.get<OpenTrivia>("trivia")) ?? null;
    await this.ctx.storage.delete("trivia");
    return t;
  }

  /** Alarm fires ~2s after the poll closes; the trivia handler's close job runs through here. */
  async alarm() {
    const t = await this.closeTrivia();
    if (!t) return;
    await this.env.TG_OPS.send({ kind: "trivia_close", roundId: t.roundId, winners: t.winners });
  }

  /** Generic per-chat cooldown: true if allowed now (and records it). */
  async cooldown(key: string, seconds: number): Promise<boolean> {
    const last = (await this.ctx.storage.get<number>(`cd:${key}`)) ?? 0;
    if (Date.now() - last < seconds * 1000) return false;
    await this.ctx.storage.put(`cd:${key}`, Date.now());
    return true;
  }
}

export function chatStub(env: Env, chatId: number) {
  return env.CHAT_DO.get(env.CHAT_DO.idFromName(String(chatId))) as unknown as ChatDO;
}
