/** External processor adapter contract. Each processor verifies its own signature and
 *  normalizes events; the membership handler is processor-agnostic. */
import type { Env } from "../../env";

export type PaymentEventKind = "initial" | "rebill" | "refund" | "chargeback";

export interface PaymentEvent {
  processor: string;
  eventId: string;          // unique per processor event; replay guard
  txnId?: string;
  kind: PaymentEventKind;
  userId: number;           // Telegram user id carried in checkout metadata
  tier: string;
  amount: number;           // minor units or Stars
  currency: string;
  subscriptionId?: string;
  periodEndAt: string;      // ISO
  occurredAt: string;       // ISO
  raw: unknown;
}

export interface PaymentProcessor {
  name: string;
  /** Build a checkout URL for this user + tier. */
  checkoutUrl(env: Env, userId: number, tier: string): Promise<string>;
  /** Verify + parse a webhook request. Return null (and the route answers 400) on bad signature. */
  parseWebhook(env: Env, req: Request): Promise<PaymentEvent | null>;
}
