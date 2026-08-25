/** One instance per Telegram user. Serializes the membership state machine so a Stars
 *  renewal, an external rebill and a join request can never race. D1 is the record;
 *  this object just orders the writes. */
import { DurableObject } from "cloudflare:workers";
import type { Env } from "../env";
import { nowIso } from "../db";
import { EMPTY_SNAPSHOT, transition, type Effect, type MemberEvent, type MemberSnapshot } from "../domain/membership";

interface Row { state: MemberSnapshot["state"]; rail: MemberSnapshot["rail"]; tier: string | null; period_end_at: string | null; grace_until: string | null }

export class MemberDO extends DurableObject<Env> {
  private async load(userId: number): Promise<MemberSnapshot> {
    const r = await this.env.DB.prepare("SELECT state, rail, tier, period_end_at, grace_until FROM memberships WHERE user_id = ?").bind(userId).first<Row>();
    return r ? { state: r.state, rail: r.rail, tier: r.tier, periodEndAt: r.period_end_at, graceUntil: r.grace_until } : EMPTY_SNAPSHOT;
  }

  async snapshot(userId: number): Promise<MemberSnapshot> {
    return this.load(userId);
  }

  /** Apply an event; persist; return the new snapshot and the effects the caller must execute. */
  async apply(userId: number, event: MemberEvent, source: string, reason?: string): Promise<{ before: MemberSnapshot; next: MemberSnapshot; effects: Effect[] }> {
    const before = await this.load(userId);
    const { next, effects } = transition(before, event);
    const t = nowIso();
    await this.env.DB.batch([
      this.env.DB.prepare(
        `INSERT INTO memberships (user_id, state, rail, tier, period_end_at, grace_until, last_transition_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT (user_id) DO UPDATE SET state = excluded.state, rail = excluded.rail, tier = excluded.tier,
           period_end_at = excluded.period_end_at, grace_until = excluded.grace_until, last_transition_at = excluded.last_transition_at`,
      ).bind(userId, next.state, next.rail, next.tier, next.periodEndAt, next.graceUntil, t),
      this.env.DB.prepare("INSERT INTO membership_transitions (user_id, from_state, to_state, reason, source, at) VALUES (?, ?, ?, ?, ?, ?)")
        .bind(userId, before.state, next.state, reason ?? event.type, source, t),
    ]);
    return { before, next, effects };
  }

  /** Try an event; return null instead of throwing when it's not valid from the current state. */
  async tryApply(userId: number, event: MemberEvent, source: string, reason?: string) {
    try { return await this.apply(userId, event, source, reason); } catch { return null; }
  }
}

export function memberStub(env: Env, userId: number) {
  return env.MEMBER_DO.get(env.MEMBER_DO.idFromName(String(userId))) as unknown as MemberDO;
}
