/** Paced Telegram side effects. Anything bulk or slow goes through here. */
import { Api } from "grammy";
import type { Env, TgOp } from "../env";
import { loadConfig } from "../config";
import { dm, ephemeral, groupSay, kick, unban } from "../services/telegram";
import { closeTriviaRound } from "../handlers/games/trivia";

export async function consumeTgOp(env: Env, ctx: ExecutionContext, op: TgOp | { kind: "trivia_close"; roundId: number; winners: number[] }) {
  const api = new Api(env.TG_BOT_TOKEN);
  const cfg = await loadConfig(env);
  switch (op.kind) {
    case "kick":
      for (const chat of [cfg.groupChatId, cfg.channelChatId]) if (chat) await kick(api, chat, op.userId).catch((e) => console.warn("kick failed", chat, String(e)));
      break;
    case "unban":
      for (const chat of [cfg.groupChatId, cfg.channelChatId]) if (chat) await unban(api, chat, op.userId).catch(() => {});
      break;
    case "dm":
      await dm(api, op.userId, op.text);
      break;
    case "group_message":
      await groupSay(api, cfg, op.text, { effectId: op.effectId });
      break;
    case "ephemeral":
      await ephemeral(api, op.chatId, op.userId, op.text, { replyTo: op.replyTo });
      break;
    case "broadcast": {
      const rows = await env.DB.prepare("SELECT user_id FROM memberships WHERE state IN ('active','grace')").all<{ user_id: number }>();
      for (const r of rows.results) {
        await dm(api, r.user_id, op.text);
        await new Promise((res) => setTimeout(res, 60)); // ~16/s, under Telegram's 30/s
      }
      break;
    }
    case "trivia_close":
      await closeTriviaRound(env, ctx, cfg, api, op.roundId, op.winners);
      break;
  }
}
