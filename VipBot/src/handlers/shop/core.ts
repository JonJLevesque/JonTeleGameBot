/** Shop: items, purchases, auto-fulfillment, admin queue, stale-order refunds. No grammY here. */
import type { Api } from "grammy";
import type { Config } from "../../config";
import type { Env } from "../../env";
import { audit, nowIso } from "../../db";
import { shopDiscount } from "../../domain/levels";
import { applyPoints, getXp, InsufficientPoints } from "../../services/ledger";
import { dm, EFFECT, esc, groupSay, mention } from "../../services/telegram";
import { membershipOf, tierRank } from "../games/common";
import { MAX_SAVERS } from "../games/drops";

export interface ShopItem {
  id: number; code: string; name: string; description: string | null; price: number;
  fulfillment: "auto" | "queue"; min_tier: string | null; enabled: number; refund_after_days: number | null;
}
export interface Purchase {
  id: number; user_id: number; item_id: number; price_paid: number; status: "fulfilled" | "queued" | "refunded";
  note: string | null; created_at: string; fulfilled_at: string | null; fulfilled_by: number | null;
}

export const TITLE_MAX = 16;
export const TITLE_DAYS = 7;
export const VOTE2X_TTL_SEC = 7 * 86400;
export const PENDING_TITLE_TTL_SEC = 3600;

export const DEFAULT_ITEMS: Omit<ShopItem, "id" | "enabled">[] = [
  { code: "saver", name: "Streak saver", description: "Bridges one missed day (max 2 held).", price: 60, fulfillment: "auto", min_tier: null, refund_after_days: null },
  { code: "title7d", name: "Custom title (7 days)", description: "Your own tag next to your name in the group.", price: 150, fulfillment: "auto", min_tier: null, refund_after_days: null },
  { code: "vote2x", name: "Double vote (7 days)", description: "Your bracket votes count twice this week.", price: 80, fulfillment: "auto", min_tier: null, refund_after_days: null },
  { code: "shoutout", name: "Public shoutout", description: "A shoutout in the group, right now.", price: 200, fulfillment: "auto", min_tier: null, refund_after_days: null },
  { code: "postcredit", name: "Post credit", description: "Your name credited on an upcoming post.", price: 400, fulfillment: "queue", min_tier: null, refund_after_days: 14 },
  { code: "archive", name: "Archive access", description: "A link to the archive drop.", price: 500, fulfillment: "queue", min_tier: null, refund_after_days: null },
  { code: "ama", name: "AMA ticket", description: "One question answered personally.", price: 350, fulfillment: "queue", min_tier: null, refund_after_days: null },
  { code: "wallpaper", name: "Wallpaper pack", description: "Exclusive phone wallpapers.", price: 120, fulfillment: "queue", min_tier: null, refund_after_days: null },
  { code: "dmslot", name: "10-minute DM slot", description: "A private 10-minute chat.", price: 1500, fulfillment: "queue", min_tier: "vipplus", refund_after_days: null },
];

export async function seedDefaultItems(env: Env): Promise<boolean> {
  const any = await env.DB.prepare("SELECT 1 FROM shop_items LIMIT 1").first();
  if (any) return false;
  const stmt = env.DB.prepare("INSERT OR IGNORE INTO shop_items (code, name, description, price, fulfillment, min_tier, enabled, refund_after_days) VALUES (?, ?, ?, ?, ?, ?, 1, ?)");
  await env.DB.batch(DEFAULT_ITEMS.map((i) => stmt.bind(i.code, i.name, i.description, i.price, i.fulfillment, i.min_tier, i.refund_after_days)));
  return true;
}

export async function listItems(env: Env, onlyEnabled = true): Promise<ShopItem[]> {
  const r = await env.DB.prepare(`SELECT * FROM shop_items ${onlyEnabled ? "WHERE enabled = 1" : ""} ORDER BY price, id`).all<ShopItem>();
  return r.results;
}
export async function itemById(env: Env, id: number) { return env.DB.prepare("SELECT * FROM shop_items WHERE id = ?").bind(id).first<ShopItem>(); }
export async function itemByCode(env: Env, code: string) { return env.DB.prepare("SELECT * FROM shop_items WHERE code = ?").bind(code).first<ShopItem>(); }

export function discountedPrice(price: number, level: number): number {
  return Math.max(1, Math.round(price * (1 - shopDiscount(level))));
}

/** Tier gating: item.min_tier must be at or below the buyer's tier in cfg.tiers order. */
export function meetsTier(cfg: Config, item: ShopItem, buyerTier: string | null): boolean {
  if (!item.min_tier) return true;
  const need = tierRank(cfg, item.min_tier);
  if (need < 0) return true; // unknown tier code in DB → don't lock everyone out
  return tierRank(cfg, buyerTier) >= need;
}

export interface Buyer { id: number; first_name: string; username?: string }

export type BuyResult =
  | { ok: true; purchase: Purchase; item: ShopItem; price: number; balance: number; message: string }
  | { ok: false; reason: "not_member" | "tier" | "disabled" | "insufficient" | "duplicate" | "missing"; message: string };

/**
 * Buy an item. `ref` (the callback query id) makes the charge idempotent; a repeat with the
 * same ref returns `duplicate` without a second charge or purchase row.
 */
export async function purchase(env: Env, cfg: Config, api: Api, buyer: Buyer, itemId: number, ref: string): Promise<BuyResult> {
  const item = await itemById(env, itemId);
  if (!item) return { ok: false, reason: "missing", message: "That item no longer exists." };
  if (!item.enabled) return { ok: false, reason: "disabled", message: "That item is no longer available." };
  const m = await membershipOf(env, buyer.id);
  if (!m || (m.state !== "active" && m.state !== "grace")) return { ok: false, reason: "not_member", message: "Members only." };
  if (!meetsTier(cfg, item, m.tier)) return { ok: false, reason: "tier", message: `That one needs ${tierName(cfg, item.min_tier)}.` };
  const { level } = await getXp(env, buyer.id);
  const price = discountedPrice(item.price, level);

  let balance: number;
  try {
    const r = await applyPoints(env, buyer.id, -price, "shop", { ref: `buy:${ref}` });
    if (!r.applied) return { ok: false, reason: "duplicate", message: "Already processed." };
    balance = r.balance;
  } catch (e) {
    if (e instanceof InsufficientPoints) return { ok: false, reason: "insufficient", message: `Not enough ${cfg.pointsName} — that's ${price}.` };
    throw e;
  }

  const status: Purchase["status"] = item.fulfillment === "auto" ? "fulfilled" : "queued";
  const t = nowIso();
  const ins = await env.DB.prepare("INSERT INTO purchases (user_id, item_id, price_paid, status, created_at, fulfilled_at) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(buyer.id, item.id, price, status, t, status === "fulfilled" ? t : null).run();
  const purchaseId = Number(ins.meta.last_row_id);
  await audit(env, buyer.id, "shop.buy", purchaseId, { item: item.code, price });

  let message: string;
  if (item.fulfillment === "auto") {
    message = await autoFulfill(env, cfg, api, item, buyer, purchaseId);
  } else {
    message = `Queued — ${cfg.creatorName} will fulfill it. Order #${purchaseId}.`;
    const who = buyer.username ? `@${buyer.username}` : buyer.first_name;
    for (const id of adminIds(env)) await dm(api, id, `🛍 New order #${purchaseId}: <b>${esc(item.name)}</b> by ${esc(who)}\n/fulfill ${purchaseId} [note] · /refundorder ${purchaseId}`);
  }
  const p = (await env.DB.prepare("SELECT * FROM purchases WHERE id = ?").bind(purchaseId).first<Purchase>())!;
  return { ok: true, purchase: p, item, price, balance, message };
}

export function adminIds(env: Env): number[] {
  return env.ADMIN_USER_IDS.split(",").map((s) => Number(s.trim())).filter((n) => Number.isFinite(n) && n > 0);
}

function tierName(cfg: Config, code: string | null): string {
  return cfg.tiers.find((t) => t.code === code)?.name ?? code ?? "a higher tier";
}

/** Items handled by code; anything unknown with fulfillment=auto is downgraded to the queue. */
async function autoFulfill(env: Env, cfg: Config, api: Api, item: ShopItem, buyer: Buyer, purchaseId: number): Promise<string> {
  switch (item.code) {
    case "saver": {
      await env.DB.prepare(`INSERT INTO streaks (user_id, savers) VALUES (?, 1) ON CONFLICT (user_id) DO UPDATE SET savers = MIN(savers + 1, ?)`)
        .bind(buyer.id, MAX_SAVERS).run();
      const s = await env.DB.prepare("SELECT savers FROM streaks WHERE user_id = ?").bind(buyer.id).first<{ savers: number }>();
      return `🛡 Streak saver added. You hold ${s?.savers ?? 1} (max ${MAX_SAVERS}).`;
    }
    case "title7d": {
      await env.KV.put(`pending_title:${buyer.id}`, String(purchaseId), { expirationTtl: PENDING_TITLE_TTL_SEC });
      await dm(api, buyer.id, `Reply here with the title you want (up to ${TITLE_MAX} characters). It lasts ${TITLE_DAYS} days.`);
      return "Check your DMs — send me the title text.";
    }
    case "shoutout": {
      await groupSay(api, cfg, `💖 Shoutout to ${mention(buyer.id, buyer.first_name)} — thank you for being here.`, { effectId: EFFECT.heart }).catch(() => null);
      return "Shoutout posted.";
    }
    case "vote2x": {
      await env.KV.put(`vote2x:${buyer.id}`, new Date(Date.now() + VOTE2X_TTL_SEC * 1000).toISOString(), { expirationTtl: VOTE2X_TTL_SEC });
      return "Double vote active for 7 days.";
    }
    default: {
      await env.DB.prepare("UPDATE purchases SET status = 'queued', fulfilled_at = NULL WHERE id = ?").bind(purchaseId).run();
      for (const id of adminIds(env)) await dm(api, id, `🛍 New order #${purchaseId}: <b>${esc(item.name)}</b> by ${esc(buyer.first_name)} (no auto handler for "${esc(item.code)}")`);
      return `Queued — ${cfg.creatorName} will fulfill it. Order #${purchaseId}.`;
    }
  }
}

/** Second step of title7d: the user DMed their title text. */
export async function applyPendingTitle(env: Env, cfg: Config, api: Api, userId: number, text: string): Promise<string | null> {
  const key = `pending_title:${userId}`;
  const pending = await env.KV.get(key);
  if (!pending) return null;
  const title = text.trim().replace(/\s+/g, " ");
  if (!title || title.length > TITLE_MAX) return `Keep it to ${TITLE_MAX} characters.`;
  if (!cfg.groupChatId) return "The group isn't configured yet — ask the creator.";
  try {
    // A promotion with every right false is a demotion, so grant one harmless right to make the title stick.
    await api.promoteChatMember(cfg.groupChatId, userId, {
      can_manage_chat: false, can_delete_messages: false, can_manage_video_chats: true, can_restrict_members: false,
      can_promote_members: false, can_change_info: false, can_invite_users: false, can_pin_messages: false,
      can_post_stories: false, can_edit_stories: false, can_delete_stories: false, can_manage_topics: false, is_anonymous: false,
    });
    await api.setChatAdministratorCustomTitle(cfg.groupChatId, userId, title);
  } catch (e) {
    console.warn("title apply failed", String(e));
    return "Couldn't set the title (the bot may lack promote rights). The creator has been told.";
  }
  await env.KV.delete(key);
  await env.DB.prepare("UPDATE purchases SET note = ? WHERE id = ?").bind(`title:${title}`, Number(pending)).run();
  return `Done — you're "${esc(title)}" for ${TITLE_DAYS} days.`;
}

export async function openQueue(env: Env): Promise<(Purchase & { code: string; name: string; first_name: string; username: string | null })[]> {
  const r = await env.DB.prepare(
    `SELECT p.*, i.code, i.name, m.first_name, m.username FROM purchases p
     JOIN shop_items i ON i.id = p.item_id LEFT JOIN members m ON m.user_id = p.user_id
     WHERE p.status = 'queued' ORDER BY p.created_at`,
  ).all<Purchase & { code: string; name: string; first_name: string; username: string | null }>();
  return r.results;
}

export async function fulfillOrder(env: Env, api: Api, adminId: number, purchaseId: number, note?: string): Promise<string> {
  const p = await env.DB.prepare("SELECT * FROM purchases WHERE id = ?").bind(purchaseId).first<Purchase>();
  if (!p) return `No order #${purchaseId}.`;
  if (p.status !== "queued") return `Order #${purchaseId} is already ${p.status}.`;
  await env.DB.prepare("UPDATE purchases SET status = 'fulfilled', fulfilled_at = ?, fulfilled_by = ?, note = COALESCE(?, note) WHERE id = ?")
    .bind(nowIso(), adminId, note ?? null, purchaseId).run();
  const item = await itemById(env, p.item_id);
  await audit(env, adminId, "shop.fulfill", purchaseId, { note });
  await dm(api, p.user_id, `✅ Your order <b>${esc(item?.name ?? "#" + purchaseId)}</b> is fulfilled.${note ? `\n${esc(note)}` : ""}`);
  return `Order #${purchaseId} fulfilled.`;
}

/** Refund a queued order; idempotent on the order id. */
export async function refundOrder(env: Env, api: Api, actorId: number | null, purchaseId: number, why = "refunded"): Promise<string> {
  const p = await env.DB.prepare("SELECT * FROM purchases WHERE id = ?").bind(purchaseId).first<Purchase>();
  if (!p) return `No order #${purchaseId}.`;
  if (p.status !== "queued") return `Order #${purchaseId} is already ${p.status}.`;
  const upd = await env.DB.prepare("UPDATE purchases SET status = 'refunded', fulfilled_at = ?, fulfilled_by = ? WHERE id = ? AND status = 'queued'")
    .bind(nowIso(), actorId, purchaseId).run();
  if ((upd.meta.changes ?? 0) === 0) return `Order #${purchaseId} already handled.`;
  await applyPoints(env, p.user_id, p.price_paid, "refund", { ref: `refund:${purchaseId}`, actorId: actorId ?? undefined });
  await audit(env, actorId, "shop.refund", purchaseId, { why });
  const item = await itemById(env, p.item_id);
  await dm(api, p.user_id, `↩️ Order <b>${esc(item?.name ?? "#" + purchaseId)}</b> was ${esc(why)}: ${p.price_paid} points returned.`);
  return `Order #${purchaseId} refunded (${p.price_paid}).`;
}

/** Hourly: refund queued orders older than their item's refund_after_days. */
export async function refundStaleOrders(env: Env, api: Api): Promise<number> {
  const rows = await env.DB.prepare(
    `SELECT p.id FROM purchases p JOIN shop_items i ON i.id = p.item_id
     WHERE p.status = 'queued' AND i.refund_after_days IS NOT NULL
       AND p.created_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-' || i.refund_after_days || ' days')`,
  ).all<{ id: number }>();
  let n = 0;
  for (const r of rows.results) {
    await refundOrder(env, api, null, r.id, "auto-refunded (not fulfilled in time)");
    n++;
  }
  return n;
}

/** Hourly: strip custom titles bought more than TITLE_DAYS ago. */
export async function expireTitles(env: Env, cfg: Config, api: Api): Promise<number> {
  if (!cfg.groupChatId) return 0;
  const rows = await env.DB.prepare(
    `SELECT p.id, p.user_id FROM purchases p JOIN shop_items i ON i.id = p.item_id
     WHERE i.code = 'title7d' AND p.status = 'fulfilled' AND p.note LIKE 'title:%'
       AND p.fulfilled_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-${TITLE_DAYS} days')`,
  ).all<{ id: number; user_id: number }>();
  let n = 0;
  for (const r of rows.results) {
    // Only demote if no newer title purchase is still live for this user.
    const newer = await env.DB.prepare(
      `SELECT 1 FROM purchases p JOIN shop_items i ON i.id = p.item_id WHERE i.code = 'title7d' AND p.user_id = ? AND p.id > ? AND p.status = 'fulfilled' AND p.note LIKE 'title:%'`,
    ).bind(r.user_id, r.id).first();
    if (!newer) {
      await api.promoteChatMember(cfg.groupChatId, r.user_id, { can_manage_video_chats: false }).catch((e) => console.warn("title demote failed", String(e)));
    }
    await env.DB.prepare("UPDATE purchases SET note = 'title expired' WHERE id = ?").bind(r.id).run();
    n++;
  }
  return n;
}
