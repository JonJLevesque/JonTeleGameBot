/** Membership state machine as a pure transition table. */
export type MemberState = "none" | "attested" | "pending_payment" | "active" | "grace" | "lapsed" | "banned";
export type Rail = "stars" | "external";

export type MemberEvent =
  | { type: "attest" }
  | { type: "choose_rail"; rail: Rail; tier: string }
  | { type: "payment_ok"; rail: Rail; tier: string; periodEndAt: string }   // initial, rebill, or Stars sub seen
  | { type: "period_ended"; graceUntil: string }
  | { type: "grace_expired" }
  | { type: "reversed" }          // refund / chargeback
  | { type: "ban" }
  | { type: "unban" };

export interface MemberSnapshot {
  state: MemberState;
  rail: Rail | null;
  tier: string | null;
  periodEndAt: string | null;
  graceUntil: string | null;
}

export interface Transition { next: MemberSnapshot; effects: Effect[] }
export type Effect =
  | { kind: "grant_access" }              // send/approve invite links
  | { kind: "revoke_access"; ban: boolean } // ban=true keeps them out; false = kick (ban+unban)
  | { kind: "winback_dm" }
  | { kind: "renewal_reward" };

export class InvalidTransition extends Error {
  constructor(public readonly from: MemberState, public readonly event: MemberEvent["type"]) {
    super(`cannot ${event} from ${from}`);
  }
}

export function transition(s: MemberSnapshot, e: MemberEvent): Transition {
  const keep = (patch: Partial<MemberSnapshot>, effects: Effect[] = []): Transition => ({ next: { ...s, ...patch }, effects });
  switch (e.type) {
    case "attest":
      if (s.state === "none" || s.state === "lapsed") return keep({ state: "attested" });
      if (s.state === "attested" || s.state === "pending_payment") return keep({});
      throw new InvalidTransition(s.state, e.type);
    case "choose_rail":
      if (s.state === "attested" || s.state === "pending_payment" || s.state === "lapsed")
        return keep({ state: "pending_payment", rail: e.rail, tier: e.tier });
      throw new InvalidTransition(s.state, e.type);
    case "payment_ok":
      if (s.state === "banned") throw new InvalidTransition(s.state, e.type);
      {
        const wasActive = s.state === "active" || s.state === "grace";
        const effects: Effect[] = wasActive ? [{ kind: "renewal_reward" }] : [{ kind: "grant_access" }];
        return keep({ state: "active", rail: e.rail, tier: e.tier, periodEndAt: e.periodEndAt, graceUntil: null }, effects);
      }
    case "period_ended":
      if (s.state !== "active") throw new InvalidTransition(s.state, e.type);
      return keep({ state: "grace", graceUntil: e.graceUntil });
    case "grace_expired":
      if (s.state !== "grace") throw new InvalidTransition(s.state, e.type);
      return keep({ state: "lapsed", graceUntil: null }, [{ kind: "revoke_access", ban: false }, { kind: "winback_dm" }]);
    case "reversed":
      return keep({ state: "banned", periodEndAt: null, graceUntil: null }, [{ kind: "revoke_access", ban: true }]);
    case "ban":
      return keep({ state: "banned" }, [{ kind: "revoke_access", ban: true }]);
    case "unban":
      if (s.state !== "banned") throw new InvalidTransition(s.state, e.type);
      return keep({ state: "lapsed" });
  }
}

export function isActive(state: MemberState): boolean {
  return state === "active" || state === "grace";
}

export const EMPTY_SNAPSHOT: MemberSnapshot = { state: "none", rail: null, tier: null, periodEndAt: null, graceUntil: null };
