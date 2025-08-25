from ..core.db.base import get_conn, atomic

def ensure(con=None):
    # rien: géré par migrations
    return

def get_or_create(user_id: str) -> dict:
    con = get_conn()
    row = con.execute("SELECT has_started, money FROM players WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        with atomic(con):
            con.execute("INSERT INTO players(user_id, has_started, money) VALUES(?,0,0)", (user_id,))
        return {"has_started": False, "money": 0}
    return {"has_started": bool(int(row[0])), "money": int(row[1])}

def upsert(user_id: str, has_started: int, money: int) -> dict:
    with atomic():
        con = get_conn()
        con.execute(
            "INSERT INTO players(user_id, has_started, money) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET has_started=excluded.has_started, money=excluded.money",
            (user_id, int(has_started), int(money))
        )
        row = con.execute("SELECT has_started, money FROM players WHERE user_id=?", (user_id,)).fetchone()
    return {"has_started": bool(int(row[0])), "money": int(row[1])}

def add_money(user_id: str, delta: int) -> dict:
    with atomic():
        con = get_conn()
        con.execute("INSERT INTO players(user_id, has_started, money) VALUES(?,0,0) ON CONFLICT(user_id) DO NOTHING", (user_id,))
        con.execute("UPDATE players SET money = money + ? WHERE user_id=?", (int(delta), user_id))
        row = con.execute("SELECT has_started, money FROM players WHERE user_id=?", (user_id,)).fetchone()
    return {"has_started": bool(int(row[0])), "money": int(row[1])}

def top_richest(limit: int = 10) -> list[tuple[str,int]]:
    con = get_conn()
    rows = con.execute(
        "SELECT user_id, money FROM players WHERE has_started=1 ORDER BY money DESC, user_id ASC LIMIT ?",
        (int(limit),)
    ).fetchall()
    return [(r[0], int(r[1])) for r in rows]

def count_players() -> int:
    con = get_conn()
    (n,) = con.execute("SELECT COUNT(*) FROM players").fetchone()
    return int(n)
