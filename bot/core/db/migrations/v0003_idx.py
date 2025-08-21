DDL = "CREATE INDEX IF NOT EXISTS idx_actions_user_day ON actions(user_id, day);"
def apply(con): con.executescript(DDL)
