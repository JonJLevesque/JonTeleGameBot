import { describe, expect, it } from "vitest";
import { EMPTY_SNAPSHOT, InvalidTransition, transition, type MemberEvent, type MemberSnapshot, type MemberState } from "../src/domain/membership";

const pay: MemberEvent = { type: "payment_ok", rail: "external", tier: "vip", periodEndAt: "2026-04-01T00:00:00Z" };

describe("membership FSM", () => {
  it("happy path", () => {
    let s: MemberSnapshot = EMPTY_SNAPSHOT;
    s = transition(s, { type: "attest" }).next;
    expect(s.state).toBe("attested");
    s = transition(s, { type: "choose_rail", rail: "external", tier: "vip" }).next;
    expect(s.state).toBe("pending_payment");
    const t = transition(s, pay);
    expect(t.next.state).toBe("active");
    expect(t.effects).toEqual([{ kind: "grant_access" }]);
    const g = transition(t.next, { type: "period_ended", graceUntil: "2026-04-04T00:00:00Z" });
    expect(g.next.state).toBe("grace");
    const l = transition(g.next, { type: "grace_expired" });
    expect(l.next.state).toBe("lapsed");
    expect(l.effects.map((e) => e.kind)).toEqual(["revoke_access", "winback_dm"]);
    const back = transition(l.next, pay);
    expect(back.next.state).toBe("active");
    expect(back.effects).toEqual([{ kind: "grant_access" }]);
  });
  it("renewal while active rewards instead of re-granting", () => {
    const active: MemberSnapshot = { ...EMPTY_SNAPSHOT, state: "active", rail: "stars", tier: "vip" };
    expect(transition(active, pay).effects).toEqual([{ kind: "renewal_reward" }]);
    const grace: MemberSnapshot = { ...active, state: "grace" };
    expect(transition(grace, pay).next.state).toBe("active");
  });
  it("reversal bans from anywhere; payment cannot revive a ban", () => {
    const r = transition({ ...EMPTY_SNAPSHOT, state: "active" }, { type: "reversed" });
    expect(r.next.state).toBe("banned");
    expect(r.effects).toEqual([{ kind: "revoke_access", ban: true }]);
    expect(() => transition(r.next, pay)).toThrow(InvalidTransition);
    expect(transition(r.next, { type: "unban" }).next.state).toBe("lapsed");
  });
  it("every (state, event) pair either transitions or throws InvalidTransition", () => {
    const states: MemberState[] = ["none", "attested", "pending_payment", "active", "grace", "lapsed", "banned"];
    const events: MemberEvent[] = [
      { type: "attest" }, { type: "choose_rail", rail: "stars", tier: "vip" }, pay,
      { type: "period_ended", graceUntil: "x" }, { type: "grace_expired" }, { type: "reversed" }, { type: "ban" }, { type: "unban" },
    ];
    for (const state of states) for (const e of events) {
      try { transition({ ...EMPTY_SNAPSHOT, state }, e); } catch (err) { expect(err).toBeInstanceOf(InvalidTransition); }
    }
  });
});
