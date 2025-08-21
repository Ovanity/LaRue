from ..core.db.base import get_conn, atomic
import time

def get_or_create(user_id: str) -> dict:
    con = get_conn()
    row = con.execute(
        "SELECT bio, color_hex, title, cred, created_ts FROM profiles WHERE user_id=?", (user_id,)
    ).fetchone()
    if row is None:
        with atomic(con):
            con.execute("INSERT INTO profiles(user_id, bio, color_hex, title, cred) VALUES(?,?,?,?,?)",
                        (user_id, '', 'FFD166', '', 0))
        return {"bio":"", "color_hex":"FFD166", "title":"", "cred":0, "created_ts": int(time.time())}
    return {"bio": row[0], "color_hex": row[1], "title": row[2], "cred": int(row[3]), "created_ts": int(row[4])}

def upsert(user_id: str, **p) -> dict:
    cur = get_or_create(user_id)
    cur.update(p)
    with atomic():
        con = get_conn()
        con.execute(
            "INSERT INTO profiles(user_id, bio, color_hex, title, cred) VALUES(?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET bio=excluded.bio, color_hex=excluded.color_hex, "
            "title=excluded.title, cred=excluded.cred",
            (user_id, cur.get("bio",""), cur.get("color_hex","FFD166"), cur.get("title",""), int(cur.get("cred",0)))
        )
    return cur

def top_by_cred(limit:int=10) -> list[tuple[str,int]]:
    con = get_conn()
    rows = con.execute("SELECT user_id, cred FROM profiles ORDER BY cred DESC, user_id ASC LIMIT ?", (int(limit),)).fetchall()
    return [(r[0], int(r[1])) for r in rows]
