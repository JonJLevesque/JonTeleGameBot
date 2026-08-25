# VipBot

A creator's VIP community bot on Cloudflare Workers: paid access (Telegram Stars
subscriptions and an external processor), 18+ attestation, join-request gating,
and a fully gamified group chat (XP/levels, points, streaks, drops, trivia, slots,
shop). Single-creator; all branding lives in config.

## Layout
```
src/index.ts          hono app: /tg/webhook, /pay/<processor>, /health; queue + cron entry points
src/bot.ts            grammY wiring; every feature module registers itself
src/domain/           PURE rules (levels, streaks, drops, slots, membership FSM, trivia, signed callbacks) — tested in isolation
src/do/               ChatDO (per-chat: drop pacing, trivia round, cooldowns) · MemberDO (per-user: membership FSM)
src/services/         telegram helpers (ephemeral, links, kick), ledger (the only way points/XP move), payments adapters, ai
src/handlers/         funnel · membership · economy · games · shop · admin
src/jobs/             queue consumers (ai-jobs, tg-ops) and cron (reconcile, hourly sweep, weekly report, backup)
migrations/           D1 schema (forward-only)
test/                 vitest inside the Workers runtime (miniflare D1 + DOs), migrations auto-applied
```

## Setup (staging)
1. `npm install`
2. Resources already exist for this account (`wrangler.toml` has the ids). For a fresh account:
   `wrangler d1 create vipbot-staging`, `wrangler kv namespace create KV`, `wrangler r2 bucket create vipbot-backups`,
   `wrangler queues create vipbot-ai-jobs`, `wrangler queues create vipbot-tg-ops` — paste ids into `wrangler.toml`.
3. Secrets: `wrangler secret put TG_BOT_TOKEN`, `TG_WEBHOOK_SECRET` (random, [A-Za-z0-9_-]), `ADMIN_USER_IDS` (comma list),
   `CALLBACK_HMAC_KEY` (random), `PROCESSOR_FAKE_SECRET` (random), optionally `ANTHROPIC_API_KEY`.
4. `npm run migrate:remote && npm run deploy`
5. `TG_BOT_TOKEN=… TG_WEBHOOK_SECRET=… WORKER_URL=https://vipbot.<sub>.workers.dev npm run webhook`
6. In Telegram: make the bot an admin of the private channel **and** the private group (rights: invite users, ban users,
   manage topics, post messages). Then DM the bot as an admin: `/setup group <id>`, `/setup channel <id>`, `/setup tz <IANA>`.
   `@BotFather → /setprivacy → Disable` so the bot sees group messages (needed for XP and drops).

## Everyday
- Tests: `npm test` · Typecheck: `npm run typecheck` · Logs: `npx wrangler tail`
- Fake external payment on staging: `PROCESSOR_FAKE_SECRET=… WORKER_URL=… npx tsx scripts/fake-pay.ts initial <userId> vip`
- Add a real processor: implement `PaymentProcessor` in `src/services/payments/<name>.ts`, register in `PROCESSORS`.

## Compliance notes
- Content is never stored or proxied by the Worker; only ids, ledgers and attestations.
- Attestation records: user id, timestamp, policy version, language — nothing else.
- Stars rail: Telegram bills and auto-removes lapsed channel subscribers; we mirror state for the group.
- PayPal is not a viable external rail for adult digital goods (pre-approval + freezes); use an adult-friendly processor.
