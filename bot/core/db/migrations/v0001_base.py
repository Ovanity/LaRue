DDL = """
CREATE TABLE IF NOT EXISTS players (
  user_id     TEXT PRIMARY KEY,
  has_started INTEGER NOT NULL DEFAULT 0 CHECK (has_started IN (0,1)),
  money       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_players_money ON players(money DESC);

CREATE TABLE IF NOT EXISTS actions (
  user_id  TEXT NOT NULL,
  action   TEXT NOT NULL,
  last_ts  INTEGER NOT NULL DEFAULT 0,
  day      TEXT NOT NULL DEFAULT '',
  count    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, action)
);
CREATE INDEX IF NOT EXISTS idx_actions_day ON actions(day);

CREATE TABLE IF NOT EXISTS inventory (
  user_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  qty     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, item_id)
);

CREATE TABLE IF NOT EXISTS stats (
  user_id TEXT NOT NULL,
  key     TEXT NOT NULL,
  value   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS profiles (
  user_id    TEXT PRIMARY KEY,
  bio        TEXT NOT NULL DEFAULT '',
  color_hex  TEXT NOT NULL DEFAULT 'FFD166',
  title      TEXT NOT NULL DEFAULT '',
  cred       INTEGER NOT NULL DEFAULT 0,
  created_ts INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS respect_log (
  user_id TEXT NOT NULL,
  from_id TEXT NOT NULL,
  day     TEXT NOT NULL,
  delta   INTEGER NOT NULL,
  ts      INTEGER NOT NULL,
  PRIMARY KEY (user_id, from_id, day)
);
"""
def apply(con): con.executescript(DDL)
