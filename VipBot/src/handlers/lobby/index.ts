/** The Lobby: a free, public chat where the funnel starts — and the upsell floor.
 *  - greets newcomers with the pitch + Join button; /join repeats it
 *  - "New in the Lounge" tease whenever the creator posts to the channel (rate-limited)
 *  - daily win-a-pass trivia: fastest correct answer gets a 24h Lounge pass
 *  - Lobby Petals: chatting banks a few points that are waiting when they join
 *  - weekly "inside this week" digest
 *  No XP, drops, or games otherwise — those belong to the paid room. */
import { Api, InlineKeyboard, type Bot } from "grammy";
import type { Config } from "../../config";
import type { Ctx } from "../../context";
import { localDay, nowIso } from "../../db";
import type { Env } from "../../env";
import { shuffleQuiz } from "../../domain/trivia";
import { applyPoints } from "../../services/ledger";
import { esc, mention } from "../../services/telegram";
import { adminComp } from "../membership/admin";
import { pickQuestion } from "../games/trivia";

const TEASE_COOLDOWN_SEC = 2 * 3600;
const PETALS_PER_MSG = 1;
const PETALS_DAILY_CAP = 5;
const PETALS_MAX = 50;
const MEMBER_WIN_POINTS = 25;
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function inLobby(ctx: Ctx): boolean {
  return !!ctx.chat && ctx.cfg.lobbyChatId !== 0 && ctx.chat.id === ctx.cfg.lobbyChatId;
}

export function joinButton(cfg: Config, botUsername: string, label?: string): InlineKeyboard {
  return new InlineKeyboard().url(label ?? `🌸 Join ${cfg.roomNames.feed}`, `https://t.me/${botUsername}?start=lobby`);
}

function pitch(ctx: Ctx, name?: string): { text: string; kb: InlineKeyboard } {
  const c = ctx.cfg;
  const tiers = c.tiers.map((t) =>
    `${t.emoji} <b>${esc(t.name)}</b> ⭐${t.stars} / $${t.usd.toFixed(2)} — ${t.group ? `${esc(c.roomNames.feed)} + ${esc(c.roomNames.room)}` : esc(c.roomNames.feed)}`,
  ).join("\n");
  const hello = name ? `Welcome to ${esc(c.roomNames.lobby)}, ${esc(name)}. ` : "";
  const text = `${hello}This is the free room. The good stuff is behind the door:\n\n${tiers}\n\nTap below — it opens a private chat with me, takes a minute, and you're in.`;
  return { text, kb: joinButton(c, ctx.me.username) };
}

// ------------------------------------------------------------ lobby petals

export async function lobbyPetals(env: Env, userId: number): Promise<number> {
  return Number((await env.KV.get(`lobbypts:${userId}`)) ?? 0);
}

async function bankPetal(env: Env, cfg: Config, userId: number): Promise<void> {
  const day = localDay(cfg.creatorTz);
  const dayKey = `lobbyday:${userId}:${day}`;
  const today = Number((await env.KV.get(dayKey)) ?? 0);
  if (today >= PETALS_DAILY_CAP) return;
  const total = await lobbyPetals(env, userId);
  if (total >= PETALS_MAX) return;
  await env.KV.put(dayKey, String(today + 1), { expirationTtl: 2 * 86400 });
  await env.KV.put(`lobbypts:${userId}`, String(Math.min(PETALS_MAX, total + PETALS_PER_MSG)), { expirationTtl: 90 * 86400 });
}

/** Called by the welcome ritual: credits banked Lobby Petals once. Returns the amount. */
export async function redeemLobbyPetals(env: Env, userId: number): Promise<number> {
  const n = await lobbyPetals(env, userId);
  if (n <= 0) return 0;
  const r = await applyPoints(env, userId, n, "lobby_petals", { ref: `lobbypts:${userId}` });
  await env.KV.delete(`lobbypts:${userId}`);
  return r.applied ? n : 0;
}

// ------------------------------------------------------------ tease

async function teaseNewPost(env: Env, cfg: Config, api: Api, botUsername: string, kind: string) {
  if (!cfg.lobbyChatId) return;
  const pending = Number((await env.KV.get("lobby:tease:pending")) ?? 0) + 1;
  await env.KV.put("lobby:tease:pending", String(pending), { expirationTtl: 7 * 86400 });
  if (await env.KV.get("lobby:tease:cooldown")) return;
  await env.KV.put("lobby:tease:cooldown", "1", { expirationTtl: TEASE_COOLDOWN_SEC });
  await env.KV.delete("lobby:tease:pending");
  const more = pending > 1 ? ` (+${pending - 1} more since last time)` : "";
  const text = `🔒 Something new just landed in <b>${esc(cfg.roomNames.feed)}</b> — a ${kind}${more}. Members are looking at it right now.`;
  await api.sendMessage(cfg.lobbyChatId, text, { parse_mode: "HTML", reply_markup: joinButton(cfg, botUsername, "🔓 Unlock it") }).catch((e) => console.warn("tease failed", String(e)));
}

function postKind(m: { photo?: unknown; video?: unknown; video_note?: unknown; voice?: unknown; audio?: unknown; document?: unknown; paid_media?: unknown; text?: string }): string {
  if (m.paid_media) return "paid drop";
  if (m.video || m.video_note) return "video";
  if (m.photo) return "photo";
  if (m.voice || m.audio) return "voice note";
  if (m.document) return "file";
  return "post";
}

// ------------------------------------------------------------ win-a-pass trivia

/** True once the Lobby is big enough for win-a-pass trivia to be worth running. */
export async function lobbyBigEnough(cfg: Config, api: Api): Promise<boolean> {
  if (!cfg.lobbyChatId) return false;
  const n = await api.getChatMemberCount(cfg.lobbyChatId).catch(() => 0);
  return n - 1 >= cfg.lobby.minMembers; // minus the bot itself
}

export async function runLobbyTrivia(env: Env, cfg: Config, api: Api, opts: { force?: boolean } = {}): Promise<{ ok: boolean; reason?: string }> {
  if (!cfg.lobbyChatId) return { ok: false, reason: "no_lobby" };
  if (!opts.force && !(await lobbyBigEnough(cfg, api))) return { ok: false, reason: "too_small" };
  const PASS_DAYS = cfg.lobby.passDays;
  const picked = await pickQuestion(env);
  if (!picked) return { ok: false, reason: "no_questions" };
  const q = shuffleQuiz(picked.quiz, Math.random);
  const msg = await api.sendPoll(cfg.lobbyChatId, `🎟 Win a ${PASS_DAYS * 24}-hour pass to ${cfg.roomNames.feed}: ${q.question}`, q.options.map((o) => ({ text: o })), {
    type: "quiz", correct_option_ids: [q.correctIdx], is_anonymous: false, open_period: 90,
    explanation: `Fastest correct answer wins the pass. Members who win get +${MEMBER_WIN_POINTS} ${cfg.pointsName} instead.`,
  }).catch((e) => { console.warn("lobby poll failed", String(e)); return null; });
  if (!msg?.poll) return { ok: false, reason: "send_failed" };
  await env.KV.put(`lobbyquiz:${msg.poll.id}`, JSON.stringify({ correct: q.correctIdx, at: nowIso() }), { expirationTtl: 3600 });
  if (picked.bankId) await env.DB.prepare("UPDATE trivia_bank SET used_at = ? WHERE id = ?").bind(nowIso(), picked.bankId).run();
  return { ok: true };
}

async function onLobbyAnswer(ctx: Ctx): Promise<boolean> {
  const pa = ctx.pollAnswer;
  if (!pa) return false;
  const raw = await ctx.env.KV.get(`lobbyquiz:${pa.poll_id}`);
  if (!raw || !pa.user || pa.user.is_bot) return false;
  const { correct } = JSON.parse(raw) as { correct: number };
  if (pa.option_ids?.[0] !== correct) return true;
  const winKey = `lobbyquiz:winner:${pa.poll_id}`;
  if (await ctx.env.KV.get(winKey)) return true;
  await ctx.env.KV.put(winKey, String(pa.user.id), { expirationTtl: 3600 });
  const cfg = ctx.cfg;
  const uid = pa.user.id;
  const ms = await ctx.env.DB.prepare("SELECT state FROM memberships WHERE user_id = ?").bind(uid).first<{ state: string }>();
  if (ms && (ms.state === "active" || ms.state === "grace")) {
    await applyPoints(ctx.env, uid, MEMBER_WIN_POINTS, "lobby_trivia", { ref: `lobbyquiz:${pa.poll_id}` });
    await ctx.api.sendMessage(cfg.lobbyChatId, `🏆 ${mention(uid, pa.user.first_name)} was fastest — already a member, so +${MEMBER_WIN_POINTS} ${esc(cfg.pointsName)} inside.`, { parse_mode: "HTML" });
    return true;
  }
  const PASS_DAYS = cfg.lobby.passDays;
  const r = await adminComp(ctx.env, ctx.api, cfg, 0, uid, cfg.tiers[0]!.code, PASS_DAYS, "lobby_trivia");
  const text = r.ok
    ? `🏆 ${mention(uid, pa.user.first_name)} was fastest and wins a <b>${PASS_DAYS * 24}-hour pass</b> to ${esc(cfg.roomNames.feed)} — check your DMs. Everyone else: tomorrow, same time.`
    : `🏆 ${mention(uid, pa.user.first_name)} was fastest — but I couldn't issue the pass (${esc(r.note)}). Send me /start and I'll sort it.`;
  await ctx.api.sendMessage(cfg.lobbyChatId, text, { parse_mode: "HTML", reply_markup: joinButton(cfg, ctx.me.username) });
  return true;
}

// ------------------------------------------------------------ weekly digest

export async function postLobbyDigest(env: Env, cfg: Config, api: Api, botUsername: string) {
  if (!cfg.lobbyChatId) return;
  const since = new Date(Date.now() - 7 * 86400000).toISOString();
  const joined = await env.DB.prepare("SELECT COUNT(DISTINCT user_id) AS n FROM membership_transitions WHERE to_state = 'active' AND from_state != 'active' AND from_state != 'grace' AND at >= ?").bind(since).first<{ n: number }>();
  const crates = await env.DB.prepare("SELECT COUNT(*) AS n FROM drops WHERE claimed_at >= ? AND kind = 'crate'").bind(since).first<{ n: number }>();
  const top = await env.DB.prepare("SELECT m.first_name, SUM(x.delta) AS v FROM xp_events x JOIN members m ON m.user_id = x.user_id WHERE x.at >= ? GROUP BY x.user_id ORDER BY v DESC LIMIT 1").bind(since).first<{ first_name: string; v: number }>();
  const posts = await env.DB.prepare("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'channel_post' AND at >= ?").bind(since).first<{ n: number }>();
  const lines = [
    `📮 <b>Inside ${esc(cfg.roomNames.feed)} this week</b>`,
    posts?.n ? `• ${posts.n} new post${posts.n === 1 ? "" : "s"} from ${esc(cfg.creatorName)}` : null,
    joined?.n ? `• ${joined.n} new member${joined.n === 1 ? "" : "s"} walked in` : null,
    crates?.n ? `• ${crates.n} crate${crates.n === 1 ? "" : "s"} claimed in ${esc(cfg.roomNames.room)}` : null,
    top ? `• Top fan: <b>${esc(top.first_name)}</b>` : null,
    `• Win-a-pass trivia here every ${WEEKDAYS[cfg.lobby.triviaWeekday]} at ${String(cfg.lobby.triviaHour).padStart(2, "0")}:00`,
  ].filter(Boolean);
  await api.sendMessage(cfg.lobbyChatId, lines.join("\n"), { parse_mode: "HTML", reply_markup: joinButton(cfg, botUsername) }).catch((e) => console.warn("digest failed", String(e)));
}

// ------------------------------------------------------------ registration

export function registerLobby(bot: Bot<Ctx>) {
  bot.on("chat_member", async (ctx, next) => {
    try {
      const upd = ctx.chatMember;
      if (inLobby(ctx) && !upd.new_chat_member.user.is_bot) {
        const inStatuses = ["member", "administrator", "creator"];
        const was = inStatuses.includes(upd.old_chat_member.status);
        const now = inStatuses.includes(upd.new_chat_member.status);
        if (!was && now) {
          const { text, kb } = pitch(ctx, upd.new_chat_member.user.first_name);
          await ctx.api.sendMessage(ctx.chat!.id, text, { parse_mode: "HTML", reply_markup: kb });
        }
      }
    } catch (e) { console.error("lobby welcome failed", String(e)); }
    await next();
  });

  bot.command(["join", "vip"], async (ctx, next) => {
    if (!inLobby(ctx)) return next();
    const { text, kb } = pitch(ctx);
    await ctx.reply(text, { parse_mode: "HTML", reply_markup: kb, reply_parameters: { message_id: ctx.msg.message_id } });
  });
  bot.command("start", async (ctx, next) => {
    if (!inLobby(ctx)) return next();
    const { text, kb } = pitch(ctx);
    await ctx.reply(text, { parse_mode: "HTML", reply_markup: kb });
  });

  // Chatter banks Lobby Petals (silently).
  bot.on("message:text", async (ctx, next) => {
    if (inLobby(ctx) && ctx.from && !ctx.from.is_bot && !ctx.message.text.startsWith("/")) ctx.defer(bankPetal(ctx.env, ctx.cfg, ctx.from.id));
    await next();
  });

  // Creator posts in the channel → tease the Lobby.
  bot.on("channel_post", async (ctx, next) => {
    const post = ctx.channelPost;
    if (ctx.cfg.channelChatId && post.chat.id === ctx.cfg.channelChatId) {
      ctx.defer(ctx.env.DB.prepare("INSERT INTO audit_log (actor_id, action, target, payload_json, at) VALUES (NULL, 'channel_post', ?, NULL, ?)").bind(String(post.message_id), nowIso()).run());
      ctx.defer(teaseNewPost(ctx.env, ctx.cfg, ctx.api, ctx.me.username, postKind(post as never)));
    }
    await next();
  });

  // Win-a-pass answers. Registered before games; passes through anything that isn't ours.
  bot.on("poll_answer", async (ctx, next) => {
    try { if (await onLobbyAnswer(ctx)) return; } catch (e) { console.error("lobby answer failed", String(e)); }
    await next();
  });
}
