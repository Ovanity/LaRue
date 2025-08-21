DDL = """
CREATE TABLE IF NOT EXISTS ledger (
  user_id TEXT NOT NULL,
  key     TEXT NOT NULL,
  delta   INTEGER NOT NULL,
  reason  TEXT NOT NULL DEFAULT '',
  ts      INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  PRIMARY KEY (user_id, key)
);
CREATE INDEX IF NOT EXISTS idx_ledger_user_ts ON ledger(user_id, ts);
"""
def apply(con): con.executescript(DDL)
