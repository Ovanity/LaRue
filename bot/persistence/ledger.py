from ..core.db.base import get_conn, atomic

def add_once(user_id: str, key: str, delta: int, reason: str="") -> bool:
    with atomic():
        con = get_conn()
        before = con.total_changes
        con.execute("INSERT OR IGNORE INTO ledger(user_id, key, delta, reason) VALUES(?,?,?,?)",
                    (user_id, key, int(delta), reason or ""))
        return (con.total_changes - before) > 0

def sum_balance(user_id: str) -> int:
    con = get_conn()
    (s,) = con.execute("SELECT COALESCE(SUM(delta),0) FROM ledger WHERE user_id=?", (user_id,)).fetchone()
    return int(s)

def top_richest(limit: int = 10) -> list[tuple[str, int]]:
    with get_conn() as con:
        rows = con.execute(
            """
            SELECT user_id, COALESCE(SUM(delta), 0) AS bal
            FROM ledger
            GROUP BY user_id
            ORDER BY bal DESC
            LIMIT ?;
            """,
            (int(limit),)
        ).fetchall()
        return [(r[0], int(r[1] or 0)) for r in rows]