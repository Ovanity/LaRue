from ..core.db.base import get_conn, atomic

def get_state(user_id: str, action: str):
    con = get_conn()
    row = con.execute(
        "SELECT last_ts, day, count FROM actions WHERE user_id=? AND action=?", (user_id, action)
    ).fetchone()
    if row is None:
        return {"last_ts": 0, "day": "", "count": 0}
    return {"last_ts": int(row[0]), "day": str(row[1]), "count": int(row[2])}

def touch(user_id: str, action: str, now: int, day: str, new_count: int):
    with atomic():
        con = get_conn()
        con.execute(
            "INSERT INTO actions(user_id, action, last_ts, day, count) VALUES(?,?,?,?,?) "
            "ON CONFLICT(user_id, action) DO UPDATE SET last_ts=excluded.last_ts, day=excluded.day, count=excluded.count",
            (user_id, action, int(now), day, int(new_count))
        )
