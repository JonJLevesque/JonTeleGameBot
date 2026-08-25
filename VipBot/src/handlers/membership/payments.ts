import type { Env } from "../../env";
import type { PaymentEvent } from "../../services/payments/types";

export async function handlePaymentEvent(_env: Env, _ctx: ExecutionContext, _evt: PaymentEvent): Promise<{ ok: boolean; note?: string }> {
  return { ok: false, note: "not implemented" };
}
