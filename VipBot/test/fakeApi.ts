import type { Api } from "grammy";

/** Records Bot API calls; returns plausible payloads for the methods the games/shop modules use. */
export function fakeApi() {
  const calls: { method: string; args: unknown[] }[] = [];
  let msgId = 100;
  const raw = new Proxy({}, {
    get: (_t, method: string) => async (payload: unknown) => { calls.push({ method: `raw.${method}`, args: [payload] }); return { message_id: ++msgId }; },
  });
  const api = new Proxy({ raw }, {
    get: (t, method: string) => {
      if (method === "raw") return t.raw;
      return async (...args: unknown[]) => {
        calls.push({ method, args });
        switch (method) {
          case "sendMessage": return { message_id: ++msgId, chat: { id: args[0] } };
          case "sendPoll": return { message_id: ++msgId, poll: { id: `poll-${msgId}` } };
          case "sendDice": return { message_id: ++msgId, dice: { emoji: "🎰", value: 64 } };
          default: return true;
        }
      };
    },
  }) as unknown as Api;
  return { api, calls, of: (m: string) => calls.filter((c) => c.method === m) };
}
