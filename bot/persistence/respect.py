from ..core.db.base import get_conn, atomic

def can_give(from_id: str, to_id: str, day: str) -> tuple[bool, str|None]:
    if from_id == to_id: return False, "😅 Tu peux pas te respecter toi-même."
    con = get_conn()
    row = con.execute("SELECT 1 FROM respect_log WHERE user_id=? AND from_id=? AND day=?", (to_id, from_id, day)).fetchone()
    if row: return False, "⏳ Tu as déjà donné du respect à cette personne aujourd’hui."
    return True, None

def give(from_id: str, to_id: str, day: str) -> int:
    ok, why = can_give(from_id, to_id, day)
    if not ok: raise ValueError(why or "not allowed")
    with atomic():
        con = get_conn()
        con.execute("INSERT INTO profiles(user_id, bio, color_hex, title, cred) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(user_id) DO NOTHING", (to_id, '', 'FFD166', '', 0))
        con.execute("INSERT OR IGNORE INTO respect_log(user_id, from_id, day, delta, ts) "
                    "VALUES(?,?,?,1,strftime('%s','now'))", (to_id, from_id, day))
        con.execute("UPDATE profiles SET cred = cred + 1 WHERE user_id=?", (to_id,))
        (cred,) = con.execute("SELECT cred FROM profiles WHERE user_id=?", (to_id,)).fetchone()
    return int(cred)
