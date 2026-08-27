/** Admin commands. Private chat + ctx.isAdmin only; silently ignored elsewhere. Every action is audited. */
import { InputFile, type Bot } from "grammy";
import type { Ctx } from "../../context";
import { setConfig } from "../../config";
import { audit, findMemberByUsername, getMember, type MemberRow } from "../../db";
import { applyPoints, applyXp } from "../../services/ledger";
import { dm, esc } from "../../services/telegram";
import type { Env } from "../../env";
import { computeStats, formatStats, QUIET_DAYS } from "./stats";
import { exportCsv } from "./export";
import { seedAwards, slugify } from "../economy/awards";
import { getStreak, saveStreak } from "../economy/claim";
import { adminBan, adminKick, adminRefundStars, adminUnban, listMembers, adminComp } from "./membership-bridge";

function adminDm(ctx: Ctx): boolean {
  return ctx.chat?.type === "private" && ctx.isAdmin;
}

function args(ctx: Ctx): string[] {
  return (ctx.match ? String(ctx.match) : "").trim().split(/\s+/).filter(Boolean);
}

/** Tokenize with double-quoted phrases: `@u "Badge Name" 10 5` → ['@u','Badge Name','10','5'] */
export function tokenize(s: string): string[] {
  const out: string[] = [];
  const re = /"([^"]*)"|(\S+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) out.push(m[1] ?? m[2]!);
  return out;
}

async function target(ctx: Ctx, handle: string | undefined): Promise<MemberRow | null> {
  if (!handle) return null;
  if (/^\d+$/.test(handle)) return getMember(ctx.env, Number(handle));
  return findMemberByUsername(ctx.env, handle);
}

/** Active members not seen in the group for QUIET_DAYS. */
async function quietMembers(env: Env) {
  const cutoff = new Date(Date.now() - QUIET_DAYS * 86400000).toISOString();
  const r = await env.DB.prepare(
    `SELECT ms.user_id, m.username, m.first_name, ms.state, ms.tier, ms.period_end_at, m.last_seen_at
     FROM memberships ms JOIN members m ON m.user_id = ms.user_id WHERE ms.state = 'active' AND m.last_seen_at < ? ORDER BY m.last_seen_at`,
  ).bind(cutoff).all<{ user_id: number; username: string | null; first_name: string; state: string; tier: string | null; period_end_at: string | null; last_seen_at: string }>();
  return r.results;
}

const adminIds = (ctx: Ctx) => ctx.env.ADMIN_USER_IDS.split(",").map((s) => Number(s.trim())).filter(Boolean);

async function setupText(ctx: Ctx): Promise<string> {
  const c = ctx.cfg;
  return [
    `<b>${esc(c.communityName)}</b> by ${esc(c.creatorName)}`,
    `lobby: <code>${c.lobbyChatId}</code> · channel: <code>${c.channelChatId}</code> · group: <code>${c.groupChatId}</code>`,
    `tz: ${esc(c.creatorTz)} · ai: ${c.aiEnabled ? "on" : "off"} (${esc(c.aiModel)})`,
    `tiers: ${c.tiers.map((t) => `${t.emoji} ${esc(t.code)} ${t.stars}⭐/$${t.usd}`).join(", ")}`,
    "", "/setup lobby|channel|group &lt;id&gt; · names &lt;lobby&gt; | &lt;feed&gt; | &lt;room&gt; · tz &lt;IANA&gt; · name &lt;text&gt; · creator &lt;text&gt; · ai on|off · price &lt;tier&gt; &lt;stars&gt; &lt;usd&gt; · access &lt;tier&gt; feed|both",
  ].join("\n");
}

async function setAi(ctx: Ctx, on: boolean) {
  await setConfig(ctx.env, "aiEnabled", on);
  await audit(ctx.env, ctx.from!.id, "setup.ai", undefined, { on });
  await ctx.reply(`AI ${on ? "enabled" : "disabled"}.`);
}

import { registerAssistant } from "./assistant";
import { runLobbyTrivia } from "../lobby";

export function registerAdmin(bot: Bot<Ctx>) {
  registerAssistant(bot);
  // Bot promoted/added somewhere → tell admins the chat id.
  bot.on("my_chat_member", async (ctx, next) => {
    const m = ctx.myChatMember;
    const st = m.new_chat_member.status;
    if ((st === "administrator" || st === "member") && m.chat.type !== "private") {
      const title = (m.chat as { title?: string }).title ?? String(m.chat.id);
      for (const id of adminIds(ctx)) ctx.defer(dm(ctx.api, id, `Added to <b>${esc(title)}</b> (<code>${m.chat.id}</code>). Use /setup lobby|channel|group ${m.chat.id} (lobby = free chat, channel = paid feed, group = VIP+ chat).`));
    }
    await next();
  });

  bot.command("setup", async (ctx) => {
    if (!adminDm(ctx)) return;
    const a = args(ctx);
    const uid = ctx.from!.id;
    if (!a.length) { await ctx.reply(await setupText(ctx), { parse_mode: "HTML" }); return; }
    const [what, ...rest] = a;
    const num = Number(rest[0]);
    switch (what) {
      case "group": case "channel": case "lobby": {
        if (!Number.isInteger(num)) { await ctx.reply("Need a numeric chat id."); return; }
        const key = what === "group" ? "groupChatId" : what === "channel" ? "channelChatId" : "lobbyChatId";
        await setConfig(ctx.env, key, num);
        await audit(ctx.env, uid, `setup.${what}`, num);
        await ctx.reply(`${what} set to ${num}.`); return;
      }
      case "tz": {
        const tz = rest[0] ?? "";
        try { new Intl.DateTimeFormat("en-US", { timeZone: tz }); } catch { await ctx.reply("Unknown IANA timezone."); return; }
        await setConfig(ctx.env, "creatorTz", tz);
        await audit(ctx.env, uid, "setup.tz", tz);
        await ctx.reply(`Timezone set to ${tz}.`); return;
      }
      case "name": case "creator": {
        const v = rest.join(" ");
        if (!v) { await ctx.reply("Need a value."); return; }
        const key = what === "name" ? "communityName" : "creatorName";
        await setConfig(ctx.env, key, v);
        await audit(ctx.env, uid, `setup.${what}`, v);
        await ctx.reply(`${key} set.`); return;
      }
      case "ai": {
        if (rest[0] !== "on" && rest[0] !== "off") { await ctx.reply("Usage: /setup ai on|off"); return; }
        await setAi(ctx, rest[0] === "on"); return;
      }
      case "access": {
        const [code, what] = rest;
        const tiers = structuredClone(ctx.cfg.tiers);
        const t = tiers.find((x) => x.code === code);
        if (!t || (what !== "feed" && what !== "both")) { await ctx.reply("Usage: /setup access <tierCode> feed|both"); return; }
        t.group = what === "both";
        await setConfig(ctx.env, "tiers", tiers);
        await audit(ctx.env, uid, "setup.access", code, { group: t.group });
        await ctx.reply(`${t.emoji} ${t.name} now unlocks ${t.group ? "the feed and the room" : "the feed only"}.`);
        return;
      }
      case "names": {
        const parts = rest.join(" ").split("|").map((s) => s.trim());
        if (parts.length !== 3 || parts.some((p) => !p)) { await ctx.reply("Usage: /setup names the Lobby | the Lounge | the Backroom"); return; }
        const roomNames = { lobby: parts[0]!, feed: parts[1]!, room: parts[2]! };
        await setConfig(ctx.env, "roomNames", roomNames);
        await audit(ctx.env, uid, "setup.names", undefined, roomNames);
        await ctx.reply(`Rooms are now ${roomNames.lobby} → ${roomNames.feed} → ${roomNames.room}.`);
        return;
      }
      case "lobbytrivia": {
        // /setup lobbytrivia <weekday 0-6> <hour> [passDays] [minMembers]
        const nums = rest.map(Number);
        const wd = nums[0] ?? NaN, hr = nums[1] ?? NaN, pd = nums[2] ?? NaN, mm = nums[3] ?? NaN;
        if (!Number.isInteger(wd) || wd < 0 || wd > 6 || !Number.isInteger(hr) || hr < 0 || hr > 23) { await ctx.reply("Usage: /setup lobbytrivia <weekday 0=Sun…6=Sat> <hour 0-23> [passDays] [minMembers]"); return; }
        const lobby = { ...ctx.cfg.lobby, triviaWeekday: wd, triviaHour: hr, ...(Number.isInteger(pd) && pd > 0 ? { passDays: pd } : {}), ...(Number.isInteger(mm) && mm >= 0 ? { minMembers: mm } : {}) };
        await setConfig(ctx.env, "lobby", lobby);
        await audit(ctx.env, uid, "setup.lobbytrivia", undefined, lobby);
        await ctx.reply(`Win-a-pass trivia: weekday ${wd} at ${hr}:00, ${lobby.passDays}-day pass, needs ${lobby.minMembers}+ in the Lobby.`);
        return;
      }
      case "price": {
        const [code, stars, usd] = rest;
        const tiers = structuredClone(ctx.cfg.tiers);
        const t = tiers.find((x) => x.code === code);
        if (!t || !Number.isInteger(Number(stars)) || !Number.isFinite(Number(usd))) { await ctx.reply("Usage: /setup price <tierCode> <stars> <usd>"); return; }
        t.stars = Number(stars); t.usd = Number(usd);
        await setConfig(ctx.env, "tiers", tiers);
        await audit(ctx.env, uid, "setup.price", code, { stars: t.stars, usd: t.usd });
        await ctx.reply(`${t.name}: ${t.stars}⭐ / $${t.usd}.`); return;
      }
      default:
        await ctx.reply(await setupText(ctx), { parse_mode: "HTML" });
    }
  });

  bot.command("ai", async (ctx) => {
    if (!adminDm(ctx)) return;
    const v = args(ctx)[0];
    if (v !== "on" && v !== "off") { await ctx.reply(`AI is ${ctx.cfg.aiEnabled ? "on" : "off"}. Usage: /ai on|off`); return; }
    await setAi(ctx, v === "on");
  });

  bot.command("stats", async (ctx) => {
    if (!adminDm(ctx)) return;
    const days = args(ctx)[0] === "30" ? 30 : 7;
    const s = await computeStats(ctx.env, days);
    await ctx.reply(`<pre>${esc(formatStats(s))}</pre>`, { parse_mode: "HTML" });
  });

  bot.command("members", async (ctx) => {
    if (!adminDm(ctx)) return;
    const f = args(ctx)[0] ?? "active";
    if (!["active", "grace", "lapsed", "quiet"].includes(f)) { await ctx.reply("Usage: /members [active|grace|lapsed|quiet]"); return; }
    const rows = f === "quiet" ? await quietMembers(ctx.env) : await listMembers(ctx.env, f as "active" | "grace" | "lapsed");
    if (!rows.length) { await ctx.reply(`No ${f} members.`); return; }
    const lines = rows.slice(0, 50).map((r) => `${r.user_id} ${r.username ? "@" + r.username : esc(r.first_name)} · ${r.tier ?? "-"} · ${r.state}${r.period_end_at ? " → " + r.period_end_at.slice(0, 10) : ""}${"last_seen_at" in r ? " · seen " + String(r.last_seen_at).slice(0, 10) : ""}`);
    await ctx.reply(`<b>${f} (${rows.length})</b>\n${lines.join("\n")}`, { parse_mode: "HTML" });
  });

  bot.command("award", async (ctx) => {
    if (!adminDm(ctx)) return;
    const [handle, name, pts, xp] = tokenize(ctx.match ? String(ctx.match) : "");
    const m = await target(ctx, handle);
    if (!m || !name) { await ctx.reply('Usage: /award @user "Badge Name" [points] [xp]'); return; }
    await seedAwards(ctx.env);
    const code = slugify(name);
    const points = Number(pts) || 0, xpN = Number(xp) || 0;
    const ref = `award:${ctx.update.update_id}`;
    await ctx.env.DB.prepare("INSERT INTO awards (code, name, emoji, description) VALUES (?, ?, '🏅', NULL) ON CONFLICT (code) DO UPDATE SET name = excluded.name").bind(code, name).run();
    await ctx.env.DB.prepare("INSERT OR REPLACE INTO member_awards (user_id, code, granted_by, note, granted_at) VALUES (?, ?, ?, NULL, ?)")
      .bind(m.user_id, code, ctx.from!.id, new Date().toISOString()).run();
    if (points > 0) await applyPoints(ctx.env, m.user_id, points, "award", { ref, actorId: ctx.from!.id });
    if (xpN > 0) await applyXp(ctx.env, m.user_id, xpN, "award", ref);
    await audit(ctx.env, ctx.from!.id, "award", m.user_id, { code, name, points, xp: xpN });
    const c = ctx.cfg;
    const extras = [points ? `+${points} ${c.pointsName}` : "", xpN ? `+${xpN} ${c.xpName}` : ""].filter(Boolean).join(" · ");
    ctx.defer(dm(ctx.api, m.user_id, `🏅 You earned the <b>${esc(name)}</b> badge${extras ? ` (${extras})` : ""}.`));
    await ctx.reply(`Awarded "${name}" to ${m.first_name}.`);
  });

  bot.command("grant", async (ctx) => {
    if (!adminDm(ctx)) return;
    const [handle, kind, nStr] = args(ctx);
    const m = await target(ctx, handle);
    const n = Number(nStr);
    if (!m || !["points", "xp", "saver"].includes(kind ?? "") || !Number.isInteger(n) || n === 0) { await ctx.reply("Usage: /grant @user points|xp|saver N"); return; }
    const ref = `grant:${ctx.update.update_id}`;
    if (kind === "points") await applyPoints(ctx.env, m.user_id, n, "grant", { ref, actorId: ctx.from!.id, clampToZero: true });
    else if (kind === "xp") { if (n < 0) { await ctx.reply("XP can't go down."); return; } await applyXp(ctx.env, m.user_id, n, "grant", ref); }
    else { const s = await getStreak(ctx.env, m.user_id); await saveStreak(ctx.env, m.user_id, { ...s, savers: Math.max(0, s.savers + n) }); }
    await audit(ctx.env, ctx.from!.id, "grant", m.user_id, { kind, n });
    await ctx.reply(`Granted ${n} ${kind} to ${m.first_name}.`);
  });

  bot.command("lobbytrivia", async (ctx) => {
    if (!adminDm(ctx)) return;
    const r = await runLobbyTrivia(ctx.env, ctx.cfg, ctx.api, { force: true });
    await ctx.reply(r.ok ? "Posted a win-a-pass question in the Lobby." : `Couldn't (${r.reason}) — is the Lobby set (/setup lobby) and the trivia bank stocked (/q add)?`);
  });

  bot.command("comp", async (ctx) => {
    if (!adminDm(ctx)) return;
    const [handle, tierCode, daysStr] = args(ctx);
    const m = await target(ctx, handle);
    const days = daysStr ? Number(daysStr) : 30;
    if (!m || !tierCode || !Number.isInteger(days) || days < 1) {
      await ctx.reply(`Usage: /comp @user <${ctx.cfg.tiers.map((t) => t.code).join("|")}> [days]\nFree membership, no payment. They must have messaged me once so I know their @username.`);
      return;
    }
    const r = await adminComp(ctx.env, ctx.api, ctx.cfg, ctx.from!.id, m.user_id, tierCode, days);
    await ctx.reply(r.ok ? `Comped ${m.first_name}: ${r.note}. Links are in their DM.` : `Couldn't: ${r.note}`);
  });

  for (const cmd of ["kick", "ban", "unban", "refund"] as const) {
    bot.command(cmd, async (ctx) => {
      if (!adminDm(ctx)) return;
      const [handle, ...rest] = args(ctx);
      const m = await target(ctx, handle);
      if (!m) { await ctx.reply(`Usage: /${cmd} @user [reason]`); return; }
      const reason = rest.join(" ") || `admin ${cmd}`;
      const actor = ctx.from!.id;
      // The membership helpers write their own audit rows.
      const fn = { kick: adminKick, ban: adminBan, unban: adminUnban, refund: adminRefundStars }[cmd];
      const r = await fn(ctx.env, ctx.api, ctx.cfg, actor, m.user_id, reason);
      await ctx.reply(`${r.ok ? "✅" : "⚠️"} ${cmd} ${m.first_name}: ${r.note}`);
    });
  }

  bot.command("broadcast", async (ctx) => {
    if (!adminDm(ctx)) return;
    const text = ctx.match ? String(ctx.match).trim() : "";
    if (!text) { await ctx.reply("Usage: /broadcast <text>"); return; }
    await ctx.env.TG_OPS.send({ kind: "broadcast", text, parseMode: "HTML", actorId: ctx.from!.id });
    await audit(ctx.env, ctx.from!.id, "broadcast", undefined, { len: text.length });
    await ctx.reply("Broadcast queued.");
  });

  bot.command("export", async (ctx) => {
    if (!adminDm(ctx)) return;
    const csv = await exportCsv(ctx.env);
    await audit(ctx.env, ctx.from!.id, "export");
    await ctx.replyWithDocument(new InputFile(new TextEncoder().encode(csv), `members-${new Date().toISOString().slice(0, 10)}.csv`));
  });
}
