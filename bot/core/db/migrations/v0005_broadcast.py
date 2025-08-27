DDL = """
CREATE TABLE IF NOT EXISTS events (
  id          TEXT PRIMARY KEY,                      -- clé métier (ex: "inspectors:2025-08-27T08:00")
  kind        TEXT NOT NULL,                         -- "inspectors" | "patch" | "leaderboard" | ...
  title       TEXT NOT NULL DEFAULT '',
  starts_at   INTEGER NOT NULL DEFAULT 0,            -- epoch seconds
  ends_at     INTEGER NOT NULL DEFAULT 0,            -- 0 si non pertinent
  payload_json TEXT NOT NULL DEFAULT '{}',           -- contenu libre par kind (JSON string)
  status      TEXT NOT NULL DEFAULT 'scheduled',     -- scheduled | published | canceled
  jump_url    TEXT NOT NULL DEFAULT '',              -- rempli après post (https://discord.com/channels/g/c/m)
  created_ts  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_events_starts ON events(starts_at);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);

CREATE TABLE IF NOT EXISTS broadcast_log (
  event_key   TEXT PRIMARY KEY,                      -- idempotence stricte (ex: "inspectors:2025-08-27T08:00")
  guild_id    TEXT NOT NULL,
  channel_id  TEXT NOT NULL,
  message_id  TEXT NOT NULL,
  jump_url    TEXT NOT NULL,
  ts          INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

def apply(con):
    con.executescript(DDL)