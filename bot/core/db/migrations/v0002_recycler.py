DDL = """
CREATE TABLE IF NOT EXISTS recycler_state (
  user_id    TEXT PRIMARY KEY,
  level      INTEGER NOT NULL DEFAULT 1,
  canettes   INTEGER NOT NULL DEFAULT 0,
  sacs       INTEGER NOT NULL DEFAULT 0,
  streak     INTEGER NOT NULL DEFAULT 0,
  last_day   INTEGER NOT NULL DEFAULT 0,
  updated_ts INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS recycler_claims (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id   TEXT NOT NULL,
  day_key   INTEGER NOT NULL,
  sacs_used INTEGER NOT NULL,
  gross     INTEGER NOT NULL,
  tax       INTEGER NOT NULL,
  net       INTEGER NOT NULL,
  ts        INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  UNIQUE(user_id, day_key)
);
CREATE INDEX IF NOT EXISTS idx_recycler_claims_user ON recycler_claims(user_id);
"""
def apply(con): con.executescript(DDL)
