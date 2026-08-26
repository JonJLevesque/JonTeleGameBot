/** The operator manual the bot answers questions from. Keep it the single source of truth
 *  for "how do I…" — it is shown to the model verbatim, so plain, complete, current. */
import type { Config } from "../../config";

export function manual(cfg: Config): string {
  const tiers = cfg.tiers.map((t) => `${t.emoji} ${t.name} (${t.code}): ⭐${t.stars}/30d or $${t.usd}; unlocks ${t.group ? "the feed AND the room" : "the feed only"}; XP ×${t.xpMultiplier}; ${t.renewalPoints} ${cfg.pointsName} on renewal`).join("\n");
  return `
COMMUNITY: "${cfg.communityName}" run by ${cfg.creatorName}. Two rooms: the CHANNEL ("the feed") where only the creator posts content,
and the GROUP ("the room") where members chat and the games live. Both are private; the bot is admin in both.

TIERS:
${tiers}
Change: /setup price <code> <stars> <usd> · /setup access <code> feed|both

HOW FANS JOIN: they DM the bot /start → confirm 18+ and no-redistribution → pick a tier → pay by Telegram Stars (subscription link,
Telegram bills monthly and auto-removes lapsed members from the channel) or by card/crypto (checkout link; currently a test processor
until a real merchant account is connected). Then the bot DMs single-use join links. Forwarded links are refused and logged.
Lapse: 3-day grace with reminder DMs, then removed with a win-back DM; they keep level/badges if they come back. Refund/chargeback = ban.

MONEY: Stars revenue lands in the CHANNEL OWNER's balance (withdraw via Fragment, 21-day hold). Telegram pays ≈ $0.013 per Star.
Bot-side Stars tips (/tip) can be refunded with /refund @user. Channel subscriptions are refunded by Telegram, not the bot.

CREATOR COMMANDS (DM only):
/setup — show config · /setup group|channel <id> · tz <IANA> · name <text> · creator <text> · ai on|off · price … · access …
/comp @user <tier> [days] — free membership (friends, promos, testers). /kick @user · /ban @user · /unban @user · /refund @user
/members [active|grace|lapsed|quiet] · /stats [7|30] · /export (CSV) · /broadcast <text> (DM every active member)
/award @user "Badge name" [points] [xp] · /grant @user points|xp|saver N
/shop add <code> "<name>" <price> auto|queue [min_tier] [desc] · /shop edit <code> price|name|enabled|desc <value> · /shop rm <code>
/queue — orders waiting on you · /fulfill <id> [note] · /refundorder <id>
/q add <question> | <correct> | <wrong> | <wrong> [| <wrong>] · /q gen [N] [topic] (AI drafts) · /q review (approve/decline) · /q count
In the room: /drop (force a crate) · /trivia [topic] (start a round now; one runs daily at 20:00 automatically)
/request <text> — send Jon (the developer) a feature request or bug. /requests — list them.
/ai on|off — AI features: trivia drafting, weekly briefing, and this help chat.

MEMBER EXPERIENCE: /claim daily ${cfg.pointsName} with streaks (every member); /profile; /tip <stars>. Room-tier members also earn
${cfg.xpName} by chatting (capped, cooldown), get reactions credit, tap crates that drop after 35–60 messages (1 in 5 is a trap),
play trivia (fastest correct wins bonus), /slots (points sink), /give, /leaderboard, and spend in /shop (titles, shoutouts,
streak savers, creator-fulfilled perks like post credits, AMA tickets, DM slots). Levels 1–15 with titles and unlocks; level-ups are announced.

WEEKLY: Monday 09:00 (creator tz) the bot DMs admins a report: revenue by rail/tier, new/churn/grace, DAU/WAU, top ${cfg.xpName}
gainers, top tipper, shop sales, open queue, silent members — plus an AI briefing when AI is on.

LIMITS / HONEST NOTES: the bot cannot see who paid Stars until they join the channel; renewals on Stars are inferred from still being
in the channel at period end. Custom titles need the bot to have "add admins" right. Ephemeral (private) messages in the room require
the group to be a supergroup. Nothing the members post is stored by the bot — only ids, ledgers, and the 18+ attestation.
`.trim();
}
