from ..core.db.base import get_conn, atomic

def incr(user_id: str, key: str, delta: int = 1) -> int:
    with atomic():
        con = get_conn()
        con.execute(
            "INSERT INTO stats(user_id, key, value) VALUES(?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = value + excluded.value",
            (user_id, key, int(delta))
        )
        (val,) = con.execute("SELECT value FROM stats WHERE user_id=? AND key=?", (user_id, key)).fetchone()
    return int(val)

def get(user_id: str, key: str, default: int = 0) -> int:
    con = get_conn()
    row = con.execute("SELECT value FROM stats WHERE user_id=? AND key=?", (user_id, key)).fetchone()
    return int(row[0]) if row else int(default)

def all_for(user_id: str) -> dict[str,int]:
    con = get_conn()
    rows = con.execute("SELECT key, value FROM stats WHERE user_id=?", (user_id,)).fetchall()
    return {r[0]: int(r[1]) for r in rows}
