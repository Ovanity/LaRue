from ..core.db.base import get_conn, atomic

def get_inventory(user_id: str) -> dict[str,int]:
    con = get_conn()
    rows = con.execute("SELECT item_id, qty FROM inventory WHERE user_id=?", (user_id,)).fetchall()
    return {r[0]: int(r[1]) for r in rows}

def add_item(user_id: str, item_id: str, qty: int = 1):
    if qty <= 0: return
    with atomic():
        con = get_conn()
        con.execute(
            "INSERT INTO inventory(user_id, item_id, qty) VALUES(?,?,?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET qty = qty + excluded.qty",
            (user_id, item_id, int(qty))
        )
