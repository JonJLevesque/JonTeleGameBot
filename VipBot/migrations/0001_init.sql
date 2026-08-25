-- VipBot schema. All timestamps ISO-8601 UTC text unless noted.
CREATE TABLE members (
  user_id INTEGER PRIMARY KEY,
  username TEXT,
  first_name TEXT NOT NULL,
  joined_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  referrer_id INTEGER
);

CREATE TABLE attestations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  policy_version INTEGER NOT NULL,
  attested_at TEXT NOT NULL,
  lang TEXT
);
CREATE INDEX attestations_user ON attestations (user_id, policy_version);

CREATE TABLE memberships (
  user_id INTEGER PRIMARY KEY,
  state TEXT NOT NULL CHECK (state IN ('none','attested','pending_payment','active','grace','lapsed','banned')),
  rail TEXT CHECK (rail IN ('stars','external')),
  tier TEXT,
  period_end_at TEXT,
  grace_until TEXT,
  external_subscription_id TEXT,
  stars_invite_link TEXT,
  last_transition_at TEXT NOT NULL,
  in_group INTEGER NOT NULL DEFAULT 0,
  in_channel INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX memberships_state ON memberships (state, period_end_at);

CREATE TABLE membership_transitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  from_state TEXT NOT NULL,
  to_state TEXT NOT NULL,
  reason TEXT NOT NULL,
  source TEXT NOT NULL,
  at TEXT NOT NULL
);
CREATE INDEX transitions_user ON membership_transitions (user_id, id);

CREATE TABLE payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  rail TEXT NOT NULL,
  external_event_id TEXT NOT NULL UNIQUE,
  external_txn_id TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('initial','rebill','refund','chargeback','stars_sub','stars_tip','stars_purchase')),
  amount INTEGER NOT NULL,
  currency TEXT NOT NULL,
  tier TEXT,
  occurred_at TEXT NOT NULL,
  raw_json TEXT
);
CREATE INDEX payments_user ON payments (user_id, occurred_at);

CREATE TABLE invite_links (
  link TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  chat_kind TEXT NOT NULL CHECK (chat_kind IN ('group','channel')),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_by INTEGER,
  used_at TEXT
);
CREATE INDEX invite_links_user ON invite_links (user_id);

CREATE TABLE update_dedupe (
  update_id INTEGER PRIMARY KEY,
  received_at TEXT NOT NULL
);

CREATE TABLE xp_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  delta INTEGER NOT NULL,
  reason TEXT NOT NULL,
  ref_id TEXT,
  at TEXT NOT NULL,
  UNIQUE (reason, ref_id)
);
CREATE INDEX xp_events_user ON xp_events (user_id, at);

CREATE TABLE xp_totals (
  user_id INTEGER PRIMARY KEY,
  xp INTEGER NOT NULL DEFAULT 0,
  level INTEGER NOT NULL DEFAULT 0,
  announced_level INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE points_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  delta INTEGER NOT NULL,
  balance_after INTEGER NOT NULL,
  reason TEXT NOT NULL,
  ref_id TEXT,
  actor_id INTEGER,
  at TEXT NOT NULL,
  UNIQUE (reason, ref_id)
);
CREATE INDEX points_ledger_user ON points_ledger (user_id, at);

CREATE TABLE points_balances (
  user_id INTEGER PRIMARY KEY,
  balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0)
);

CREATE TABLE activity_counters (
  -- per-user per-day caps (message xp events, reactions, spins, gives, drop taps)
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,           -- YYYY-MM-DD in creator tz
  key TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  last_at TEXT,
  PRIMARY KEY (user_id, day, key)
);

CREATE TABLE awards (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  emoji TEXT NOT NULL,
  description TEXT
);

CREATE TABLE member_awards (
  user_id INTEGER NOT NULL,
  code TEXT NOT NULL,
  granted_by INTEGER,
  note TEXT,
  granted_at TEXT NOT NULL,
  PRIMARY KEY (user_id, code)
);

CREATE TABLE streaks (
  user_id INTEGER PRIMARY KEY,
  current INTEGER NOT NULL DEFAULT 0,
  best INTEGER NOT NULL DEFAULT 0,
  last_claim_date TEXT,
  savers INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE drops (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER NOT NULL,
  message_id INTEGER,
  kind TEXT NOT NULL CHECK (kind IN ('crate','trap','saver')),
  points INTEGER NOT NULL,
  xp INTEGER NOT NULL,
  spawned_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  claimed_by INTEGER,
  claimed_at TEXT
);
CREATE INDEX drops_chat ON drops (chat_id, spawned_at);

CREATE TABLE trivia_bank (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question TEXT NOT NULL,
  options_json TEXT NOT NULL,   -- JSON array, index 0 is correct
  source TEXT NOT NULL CHECK (source IN ('creator','ai','static')),
  approved INTEGER NOT NULL DEFAULT 1,
  used_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE trivia_rounds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER NOT NULL,
  poll_id TEXT UNIQUE,
  message_id INTEGER,
  bank_id INTEGER,
  correct_idx INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  closes_at TEXT NOT NULL,
  closed_at TEXT,
  winners_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE shop_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  price INTEGER NOT NULL CHECK (price > 0),
  fulfillment TEXT NOT NULL CHECK (fulfillment IN ('auto','queue')),
  min_tier TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  refund_after_days INTEGER
);

CREATE TABLE purchases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  item_id INTEGER NOT NULL,
  price_paid INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('fulfilled','queued','refunded')),
  note TEXT,
  created_at TEXT NOT NULL,
  fulfilled_at TEXT,
  fulfilled_by INTEGER
);
CREATE INDEX purchases_status ON purchases (status, created_at);

CREATE TABLE tips (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  stars INTEGER NOT NULL,
  charge_id TEXT NOT NULL UNIQUE,
  at TEXT NOT NULL
);

CREATE TABLE reports (
  week_key TEXT PRIMARY KEY,
  posted_at TEXT NOT NULL,
  stats_json TEXT NOT NULL
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_id INTEGER,
  action TEXT NOT NULL,
  target TEXT,
  payload_json TEXT,
  at TEXT NOT NULL
);

CREATE TABLE config (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL
);
