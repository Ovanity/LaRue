from ..core.db.base import get_conn, atomic
import time

def get_state(user_id: str) -> dict:
    con = get_conn()
    row = con.execute("SELECT level, canettes, sacs, streak, last_day FROM recycler_state WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        with atomic(con):
            con.execute("INSERT INTO recycler_state(user_id) VALUES(?)", (user_id,))
        return {"level":1,"canettes":0,"sacs":0,"streak":0,"last_day":0}
    return {"level":int(row[0]),"canettes":int(row[1]),"sacs":int(row[2]),"streak":int(row[3]),"last_day":int(row[4])}

def upsert_state(user_id: str, **st) -> dict:
    cur = get_state(user_id); cur.update({k:int(v) for k,v in st.items() if k in {"level","canettes","sacs","streak","last_day"}})
    with atomic():
        con = get_conn()
        con.execute(
            "INSERT INTO recycler_state(user_id, level, canettes, sacs, streak, last_day, updated_ts) "
            "VALUES(?,?,?,?,?,?, strftime('%s','now')) "
            "ON CONFLICT(user_id) DO UPDATE SET level=excluded.level, canettes=excluded.canettes, "
            "sacs=excluded.sacs, streak=excluded.streak, last_day=excluded.last_day, updated_ts=excluded.updated_ts",
            (user_id, cur["level"], cur["canettes"], cur["sacs"], cur["streak"], cur["last_day"])
        )
    return cur

def log_claim(user_id: str, day_key: int, sacs_used: int, gross: int, tax: int, net: int):
    with atomic():
        con = get_conn()
        con.execute("INSERT OR IGNORE INTO recycler_claims(user_id, day_key, sacs_used, gross, tax, net) VALUES(?,?,?,?,?,?)",
                    (user_id, int(day_key), int(sacs_used), int(gross), int(tax), int(net)))
